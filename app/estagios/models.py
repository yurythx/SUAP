import calendar
import datetime
import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

import numpy
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.aggregates import Avg, Sum
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe

from comum.models import Configuracao, User
from comum.utils import get_setor, get_uo, tl
from convenios.models import Convenio
from djtools.db import models
from djtools.templatetags.filters import format_, in_group
from djtools.utils import get_datetime_now, normalizar_nome_proprio, render_to_string, send_mail, send_notification
from documento_eletronico.models import Documento, DocumentoTexto, HipoteseLegal, ModeloDocumento
from documento_eletronico.utils import EstagioProcessamentoVariavel, get_variaveis
from edu.models import Aluno, AtividadePraticaProfissional, Aula, CursoCampus, Falta, MatriculaDiario, ModalidadePraticaProfissional, Professor, Turno
from edu.models.cadastros_gerais import Modalidade
from estagios.utils import (
    get_coordenadores_emails,
    get_coordenadores_estagio,
    get_coordenadores_nomes,
    get_coordenadores_vinculos,
    get_situacoes_irregulares,
    tem_permissao_de_coordenador,
    get_diretores_academicos,
    get_coordenadores_extensao,
    usuario_possui_cadastro,
)
from rh.models import PessoaJuridica, Servidor


class AtividadeProfissionalEfetiva(models.ModelPlus):
    TIPO_EMPREGO_CARGO_OU_FUNCAO = 1
    TIPO_ATIVIDADE_PROFISSIONAL_AUTONOMA = 2
    TIPO_ATIVIDADE_EMPRESARIAL = 3
    TIPO_PROGRAMA_APRENDIZAGEM_EXTERNO = 4
    TIPO_OUTRO = 5
    TIPO = [
        [TIPO_EMPREGO_CARGO_OU_FUNCAO, 'Emprego, Cargo ou Função'],
        [TIPO_ATIVIDADE_PROFISSIONAL_AUTONOMA, 'Atividade Profissional Autônoma'],
        [TIPO_ATIVIDADE_EMPRESARIAL, 'Atividade Empresarial'],
        [TIPO_PROGRAMA_APRENDIZAGEM_EXTERNO, 'Programa de Aprendizagem Externo'],
        [TIPO_OUTRO, 'Outro(a)'],
    ]

    EM_ANDAMENTO = 1
    CONCLUIDA = 2
    NAO_CONCLUIDA = 3
    SITUACOES = [[EM_ANDAMENTO, 'Em andamento'], [CONCLUIDA, 'Concluída'], [NAO_CONCLUIDA, 'Não concluída']]

    CANCELAMENTO_PEDIDO_ALUNO = 1
    CANCELAMENTO_FIM_VINCULO = 2
    CANCELAMENTO_INSTITUICAO_ENSINO = 3
    OUTRO_MOTIVO = 4
    MOTIVO_CANCELAMENTO_CHOICHES = [
        [CANCELAMENTO_PEDIDO_ALUNO, 'Cancelamento a pedido do(a) aluno(a)'],
        [CANCELAMENTO_FIM_VINCULO, 'Cancelamento motivado por fim de vínculo'],
        [CANCELAMENTO_INSTITUICAO_ENSINO, 'Cancelamento a pedido da Instituição de Ensino'],
        [OUTRO_MOTIVO, 'Outro motivo'],
    ]

    # Dados gerais
    aluno = models.ForeignKeyPlus(Aluno, verbose_name='Aluno')
    instituicao = models.CharFieldPlus(
        'Instituição de Realização da Atividade',
        default='',
        blank=True,
        null=True,
        help_text='Em caso de atividade profissional autônoma desnecessário o preenchimento.',
    )
    razao_social = models.CharFieldPlus(
        'Razão Social', blank=True, null=True, help_text='Em caso de profissional liberal, preencher o nome do profissional.'
    )
    orientador = models.ForeignKeyPlus(Professor, verbose_name='Orientador')
    tipo = models.IntegerField('Tipo desta Atividade Profissional Efetiva', choices=TIPO, null=True, blank=False)
    descricao_outro_tipo = models.CharFieldPlus('Descrição de Outro Tipo', null=True, blank=True)

    # Período e Carga Horária
    inicio = models.DateFieldPlus('Data de Início')
    data_prevista_encerramento = models.DateFieldPlus('Data Prevista para Encerramento')
    ch_semanal = models.PositiveSmallIntegerField('Carga Horária Semanal')

    # Documentação
    documentacao_comprobatoria = models.FileFieldPlus(
        'Documentação Comprobatória',
        blank=False,
        null=False,
        max_length=255,
        upload_to='atividade_profissional_efetiva/documentacao_comprobatoria',
        help_text='Documentação que comprove que o aluno realiza atividades '
        'compatíveis com a prática profissional exigida pelo seu '
        'curso (Ex. Cópia da Carteira de Trabalho, do Contrato de '
        'Trabalho, conselho profissional de classe, etc.)',
    )
    plano_atividades = models.FileFieldPlus(
        'Plano de Atividades',
        blank=False,
        null=False,
        max_length=255,
        upload_to='atividade_profissional_efetiva/planos_atividades',
        help_text='Plano de Atividades de acordo com a Resolução 25/2019, modelo disponível no endereço: http://portal.ifrn.edu.br/extensao/estagios-e-egressos',
    )

    # Relação das Atividades
    atividades = models.TextField('Atividades Planejadas', default='')

    # Encerramento
    anterior_20171 = models.BooleanField(
        'Atividade Profissional Efetiva anterior a 2017.1 (30/09/2017)?',
        help_text='Marcar "Sim" caso esta Atividade Profissional Efetiva tenha se encerrado até o dia 30/09/2017.',
        default=None,
        choices=[[None, '-------'], [True, 'Sim'], [False, 'Não']],
        null=True,
        blank=True,
    )
    encerramento = models.DateFieldPlus('Data de Encerramento', blank=False, null=True)
    ch_final = models.IntegerField('Carga Horária Cumprida', blank=False, null=True)
    relatorio_final_aluno = models.FileFieldPlus(
        'Declaração de Realização de Atividade Profissional Efetiva',
        blank=False,
        null=True,
        max_length=255,
        upload_to='atividade_profissional_efetiva/relatorio_final_aluno',
        help_text='Modelo disponível em: http://portal.ifrn.edu.br/extensao/estagios-e-egressos/atividade-profissional-efetiva',
    )
    observacoes = models.TextField('Observações', default='', blank=True, null=True)

    # Cadastro do Cancelamento
    cancelamento = models.DateFieldPlus(
        'Data do Cancelamento',
        null=True,
        blank=False,
        help_text='Data em que de fato não foi mais possível a realização da atividade profissional efetiva.',
    )
    motivo_cancelamento = models.IntegerField('Motivo do Encerramento', choices=MOTIVO_CANCELAMENTO_CHOICHES, null=True, blank=False)
    descricao_cancelamento = models.TextField('Descrição do Cancelamento', null=True, blank=True)

    situacao = models.IntegerField('Situação', choices=SITUACOES, null=True, blank=False, default=EM_ANDAMENTO)

    # Prazo para regularizar a matrícula
    prazo_final_regularizacao_matricula_irregular = models.DateFieldPlus('Prazo Final para Regularizar a Matrícula', null=True, blank=True)

    # Avaliação da Atividade Profissional Efetiva por parte do Aluno
    AVALICAO_CONCEITO_EXCELENTE = 1
    AVALICAO_CONCEITO_BOM = 2
    AVALICAO_CONCEITO_REGULAR = 3
    AVALICAO_CONCEITO_RUIM = 4
    AVALICAO_CONCEITO_PESSIMO = 5
    AVALICAO_CONCEITO_CHOICES = [
        [AVALICAO_CONCEITO_EXCELENTE, 'Excelente'],
        [AVALICAO_CONCEITO_BOM, 'Bom'],
        [AVALICAO_CONCEITO_REGULAR, 'Regular'],
        [AVALICAO_CONCEITO_RUIM, 'Ruim'],
        [AVALICAO_CONCEITO_PESSIMO, 'Péssimo'],
    ]

    REALIZADA_SIM = 1
    REALIZADA_NAO = 2
    PARCIALMENTE_REALIZADA = 3
    REALIZADA_CHOICES = [[REALIZADA_SIM, 'Realizadas'], [REALIZADA_NAO, 'Não Realizadas'], [PARCIALMENTE_REALIZADA, 'Parcialmente Realizadas']]

    # Atividades Previstas
    avaliacao_atividades = models.IntegerField('Sobre as Atividades', choices=REALIZADA_CHOICES, null=True, blank=False)

    # Desenvolvimento das atividades
    comentarios_atividades = models.TextField(
        'Comentários sobre o desenvolvimento das atividades',
        null=True,
        blank=True,
        help_text='Descreva atividades que foram realizadas parcialmente ou que não foram realizadas e justifique.',
    )

    # Atividades não-previstas
    outras_atividades = models.TextField('Realizou atividades não previstas no plano de atividades? Informe e justifique', blank=True, null=True)

    # relação teoria/prática (somente relatório do aprendiz)
    area_formacao = models.IntegerField(
        'Área de Formação',
        blank=False,
        null=True,
        help_text='A atividade profissional efetiva foi desenvolvida em sua área de formação?',
        choices=[[1, 'Sim'], [0, 'Não']],
    )
    contribuiu = models.IntegerField(
        'Contribuição',
        blank=False,
        null=True,
        help_text='As atividades desenvolvidas contribuíram para a sua formação?',
        choices=[[1, 'Sim'], [0, 'Não']],
    )
    aplicou_conhecimento = models.IntegerField(
        'Aplicação do Conhecimento',
        blank=False,
        null=True,
        help_text='Você teve oportunidade de aplicar os conhecimentos adquiridos no seu Curso?',
        choices=[[1, 'Sim'], [0, 'Não']],
    )

    # avaliação do aprendiz (somente relatório do aprendiz)
    avaliacao_conceito = models.IntegerField(
        'Conceito',
        help_text='Qual conceito você atribui ao desenvolvimento desta prática profissional?',
        choices=AVALICAO_CONCEITO_CHOICES,
        null=True,
        blank=False,
    )

    # Dados gerais
    data_relatorio = models.DateFieldPlus('Data da Declaração de Realização de Atividade Profissional Efetiva', blank=False, null=True)

    class Meta:
        verbose_name = 'Atividade Profissional Efetiva'
        verbose_name_plural = 'Atividades Profissionais Efetivas'

    def __str__(self):
        return f'Atividade Profissional Efetiva do(a) aluno(a) {self.aluno}'

    def get_absolute_url(self):
        return f'/estagios/atividade_profissional_efetiva/{self.pk}/'

    def get_situacao_aluno(self):
        return f'{self.aluno.situacao}'

    get_situacao_aluno.admin_order_field = 'aluno__situacao__descricao'
    get_situacao_aluno.short_description = 'Situação da Matrícula no Curso'

    def get_situacao_ultima_matricula_periodo(self):
        return f'{self.aluno.get_ultima_matricula_periodo().situacao}'

    get_situacao_ultima_matricula_periodo.admin_order_field = 'aluno__matriculaperiodo__situacao__descricao'
    get_situacao_ultima_matricula_periodo.short_description = 'Situação da Matrícula em Período'

    def get_campus(self):
        return f'{self.aluno.curso_campus.diretoria.setor.uo}'

    get_campus.admin_order_field = 'aluno__curso_campus__diretoria__setor__uo'
    get_campus.short_description = 'Campus'

    def is_concluida(self):
        return self.situacao == self.CONCLUIDA

    def is_nao_concluida(self):
        return self.situacao == self.NAO_CONCLUIDA

    def is_encerrado(self):
        return self.situacao == self.CONCLUIDA or self.situacao == self.NAO_CONCLUIDA

    def is_cancelado(self):
        return self.situacao == self.NAO_CONCLUIDA

    def is_em_andamento(self):
        return self.situacao == self.EM_ANDAMENTO

    def get_email_aluno(self):
        return self.aluno.email_notificacao

    @transaction.atomic
    def save(self):
        if not self.pk:
            super().save()
            self.notificar_aluno_inicialmente()
            self.orientador_recem_cadastrado()
        super().save()

    def notificar_aluno_inicialmente(self, user=None):
        self.save()

        titulo = '[SUAP] Cadastro de Atividade Profissional Efetiva'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_cadastrada.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'nome_orientador': self.orientador.get_nome(),
                'matricula_orientador': self.orientador.get_matricula(),
                'inicio': self.inicio,
                'data_prevista_encerramento': self.data_prevista_encerramento,
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_atividade_profissional_efetiva'),
                'versao': 'aluno',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])

        email_aluno = self.get_email_aluno()
        if email_aluno:
            notificacao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_INICIAL,
                notificador=user,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def orientador_recem_cadastrado(self, user=None):
        titulo = '[SUAP] Cadastro como Orientador de Atividade Profissional Efetiva'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_cadastrada.html',
            context={
                'nome_orientador': self.orientador.get_nome(),
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'inicio': self.inicio,
                'data_prevista_encerramento': self.data_prevista_encerramento,
                'url_atividade': f'{settings.SITE_URL}{self.get_absolute_url()}',
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_atividade_profissional_efetiva'),
                'versao': 'orientador',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificacao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_INICIAL,
                notificador=user,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_orientador_envio_relatorio_final_aluno(self, user=None):
        titulo = '[SUAP] Cadastro de Relatório Final de Atividade Profissional Efetiva'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_rel_final_cadastrado.html',
            context={
                'nome_orientador': self.orientador.get_nome(),
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'url_atividade': f'{settings.SITE_URL}{self.get_absolute_url()}',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificacao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_ENVIO_RELATORIO_FINAL_ALUNO,
                notificador=user,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def get_sugestao_ch_final(self):
        dias = numpy.busday_count(self.inicio, self.data_prevista_encerramento + datetime.timedelta(days=1))
        ch_sugerida = dias * (self.ch_semanal / 5.0)
        return (
            'Dada a data cadastrada de início e a data prevista para encerramento desta Atividade Profissional Efetiva, considerando-se apenas '
            f'os dias de trabalho (segunda a sexta), estima-se uma carga horária de {format_(ch_sugerida)} horas de trabalho. Deste '
            'total não são excluídos feriados e nem outras possíveis interrupções do trabalho na Instituição de Realização da Atividade.'
        )

    def get_periodo_duracao(self):
        if self.encerramento:
            return [self.inicio, self.encerramento]
        else:
            return [self.inicio, self.data_prevista_encerramento]

    def notificar(self, user=None):
        """
        Notifica aluno e orientador sobre pendência de submissão de relatório final do aluno.
        """
        hoje = datetime.date.today()

        if self.situacao == self.EM_ANDAMENTO:
            self.verificar_matricula_irregular()

        if self.situacao == self.EM_ANDAMENTO and self.data_prevista_encerramento <= hoje and not self.relatorio_final_aluno:
            contexto_msg = {
                'nome_orientador': self.orientador.get_nome(),
                'matricula_orientador': self.orientador.get_matricula(),
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'inicio': self.inicio,
                'data_prevista_encerramento': self.data_prevista_encerramento,
                'url_atividade': f'{settings.SITE_URL}{self.get_absolute_url()}',
            }

            titulo = '[SUAP] Pendência do Relatório Final do Aluno'

            # Notificando aluno
            contexto_msg['versao'] = 'aluno'
            mensagem = render_to_string(
                template_name='notificacoes/atividade_profissional_efetiva_rel_final_pendente.html',
                context=contexto_msg,
            )

            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])
            email_aluno = self.get_email_aluno()
            if email_aluno:
                notificao = NotificacaoAtividadeProfissionalEfetiva(
                    atividade_profissional_efetiva=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_RELATORIO_PENDENTE,
                    notificador=user,
                    email_destinatario=email_aluno,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificao.save()

            # Notificando orientador
            contexto_msg['versao'] = 'orientador'
            mensagem = render_to_string(
                template_name='notificacoes/atividade_profissional_efetiva_rel_final_pendente.html',
                context=contexto_msg,
            )

            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
            if self.orientador.vinculo.user.email:
                notificao = NotificacaoAtividadeProfissionalEfetiva(
                    atividade_profissional_efetiva=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_RELATORIO_PENDENTE,
                    notificador=user,
                    email_destinatario=self.orientador.vinculo.user.email,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificao.save()

    def verificar_matricula_irregular(self):
        # se ocorreu matrícula irregular por parte de um aluno
        if self.aluno.situacao in get_situacoes_irregulares() and not self.prazo_final_regularizacao_matricula_irregular:
            self.prazo_final_regularizacao_matricula_irregular = datetime.date.today() + relativedelta(days=7)
            self.save()
            self.notificar_aluno_matricula_irregular()
            self.notificar_orientador_aluno_matricula_irregular()
            self.notificar_coordenador_aluno_matricula_irregular()
            self.notificar_coordenacao_extensao_aluno_matricula_irregular()
        # se foi dado prazo e o aluno regularizou a matrícula
        if self.aluno.situacao not in get_situacoes_irregulares() and self.prazo_final_regularizacao_matricula_irregular:
            self.prazo_final_regularizacao_matricula_irregular = None
            self.save()
        # se a situacao irregular persistiu por mais de 7 dias
        if (
            self.aluno.situacao in get_situacoes_irregulares()
            and self.prazo_final_regularizacao_matricula_irregular
            and self.prazo_final_regularizacao_matricula_irregular < datetime.date.today()
            and not NotificacaoAtividadeProfissionalEfetiva.objects.filter(
                atividade_profissional_efetiva=self, tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_INTERRUPCAO
            ).exists()
        ):
            self.situacao = self.NAO_CONCLUIDA
            self.save()
            self.notificar_aluno_interrupcao()
            self.notificar_orientador_interrupcao()

    def notificar_aluno_matricula_irregular(self, user=None):
        titulo = '[SUAP] Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_matricula_irregular.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'situacao_aluno': self.aluno.situacao.descricao,
                'curso': self.aluno.curso_campus,
                'data_prevista_encerramento': self.data_prevista_encerramento,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                'versao': 'aluno',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])
        email_aluno = self.get_email_aluno()
        if email_aluno:
            notificao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def notificar_orientador_aluno_matricula_irregular(self, user=None):
        titulo = '[SUAP] Orientando com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_matricula_irregular.html',
            context={
                'nome_orientador': self.orientador.get_nome(),
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'versao': 'orientador',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def notificar_coordenador_aluno_matricula_irregular(self, user=None):
        titulo = '[SUAP] Aluno de Curso sob sua Coordenação com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_matricula_irregular.html',
            context={
                'nome_coordenador': self.aluno.curso_campus.coordenador.nome,
                'nome_orientador': self.orientador.get_nome(),
                'matricula_orientador': self.orientador.get_matricula(),
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'versao': 'coordenador_do_curso',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.curso_campus.coordenador])
        if self.aluno.curso_campus.coordenador.user.email:
            notificao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.aluno.curso_campus.coordenador.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def notificar_coordenacao_extensao_aluno_matricula_irregular(self, user=None):
        coordenadores = get_coordenadores_estagio(self.aluno)
        coordenadores_emails = get_coordenadores_emails(coordenadores)
        coordenadores_vinculos = get_coordenadores_vinculos(coordenadores)

        titulo = '[SUAP] Atividade Profissional Efetiva com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_matricula_irregular.html',
            context={
                'nomes_coordenadores': get_coordenadores_nomes(coordenadores),
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                'versao': 'coordenacao_de_extensao',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, coordenadores_vinculos)
        if coordenadores_emails:
            notificao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=coordenadores_emails,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def get_data_envio_notificacao(self):
        return self.prazo_final_regularizacao_matricula_irregular + relativedelta(days=-7)

    def notificar_aluno_interrupcao(self, user=None):
        titulo = '[SUAP] Interrupção de Atividade Profissional Efetiva'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_interrupcao.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'data_envio_notificacao': self.get_data_envio_notificacao(),
                'versao': 'aluno',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])
        email_aluno = self.get_email_aluno()
        if email_aluno:
            notificao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_INTERRUPCAO,
                notificador=None,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def notificar_orientador_interrupcao(self, user=None):
        titulo = '[SUAP] Interrupção de Atividade Profissional Efetiva'
        mensagem = render_to_string(
            template_name='notificacoes/atividade_profissional_efetiva_interrupcao.html',
            context={
                'nome_orientador': self.orientador.get_nome(),
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'versao': 'orientador',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificao = NotificacaoAtividadeProfissionalEfetiva(
                atividade_profissional_efetiva=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_INTERRUPCAO,
                notificador=None,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()


class OrientacaoAtividadeProfissionalEfetiva(models.ModelPlus):
    atividade_profissional_efetiva = models.ForeignKeyPlus(AtividadeProfissionalEfetiva, verbose_name='Atividade Profissional Efetiva')
    orientador = models.ForeignKeyPlus(Professor, verbose_name='Orientador')
    data = models.DateFieldPlus(verbose_name='Data da Orientação')
    meio = models.CharFieldPlus('Meio/Modalidade Utilizada', blank=True, null=True, help_text='E-mail, presencial, reunião, etc.')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    local = models.CharFieldPlus('Local', blank=True, null=True)
    descricao = models.TextField('Descrição do Conteúdo da Orientação', blank=True, null=True)

    class Meta:
        ordering = ('-data',)

    def save(self):
        if self.data and (
            self.data > datetime.date.today() or (self.data == datetime.date.today() and self.hora_inicio > datetime.datetime.now().time())
        ):
            titulo = '[SUAP] Orientação de Atividade Profissional Efetiva Agendada'
            mensagem = render_to_string(
                template_name='notificacoes/atividade_profissional_efetiva_orientacao_agendada.html',
                context={
                    'nome_aluno': normalizar_nome_proprio(self.atividade_profissional_efetiva.aluno.get_nome_social_composto()),
                    'url_atividade': f'{settings.SITE_URL}{self.atividade_profissional_efetiva.get_absolute_url()}',
                },
            )

            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.atividade_profissional_efetiva.aluno.get_vinculo()])
            email_aluno = self.atividade_profissional_efetiva.get_email_aluno()
            if email_aluno:
                notificao = NotificacaoAtividadeProfissionalEfetiva(
                    atividade_profissional_efetiva=self.atividade_profissional_efetiva,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoAtividadeProfissionalEfetiva.NOTIFICACAO_AGENDAMENTO_ORIENTACAO,
                    notificador=self.user,
                    email_destinatario=email_aluno,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificao.save()
        super().save()

    def __str__(self):
        return f'Orientação de Atividade Profissional Efetiva (data: {format_(self.data)}, hora: {self.hora_inicio.hour}:{self.hora_inicio.minute}, local: {self.local})'


class NotificacaoAtividadeProfissionalEfetiva(models.ModelPlus):
    NOTIFICACAO_INICIAL = 1
    NOTIFICACAO_RELATORIO_PENDENTE = 2
    NOTIFICACAO_MATRICULA_IRREGULAR = 3
    NOTIFICACAO_INTERRUPCAO = 4
    NOTIFICACAO_ENVIO_RELATORIO_FINAL_ALUNO = 5
    NOTIFICACAO_AGENDAMENTO_ORIENTACAO = 6
    NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE = 7

    TIPO_CHOICES = [
        [NOTIFICACAO_INICIAL, 'Notificação inicial.'],
        [NOTIFICACAO_RELATORIO_PENDENTE, 'Notificação de Pendência de Relatório do Aluno.'],
        [NOTIFICACAO_MATRICULA_IRREGULAR, 'Notificação de Matrícula Irregular do Aluno.'],
        [NOTIFICACAO_INTERRUPCAO, 'Notificação de Interrupção do Cadastro de Atividade Profissional Efetiva.'],
        [NOTIFICACAO_ENVIO_RELATORIO_FINAL_ALUNO, 'Notificação de Cadastro de Relatório Final de Atividade Profissional Efetiva.'],
        [NOTIFICACAO_AGENDAMENTO_ORIENTACAO, 'Notificação de Agendamento de Orientação.'],
        [NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE, 'Notificação de Necessidade de Atualização do Plano de Atividades de Estágio.'],
    ]

    atividade_profissional_efetiva = models.ForeignKeyPlus(AtividadeProfissionalEfetiva, verbose_name='Atividade Profissional Efetiva')
    notificador = models.ForeignKeyPlus('comum.User', verbose_name='Notificador', null=True)
    data = models.DateTimeFieldPlus('Data da Notificação')
    tipo = models.IntegerField('Tipo', choices=TIPO_CHOICES)
    email_destinatario = models.TextField('E-mail')
    mensagem_enviada = models.TextField('Mensagem Enviada')

    class Meta:
        ordering = ('-data',)
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'

    def __str__(self):
        return f'{self.pk}-{self.get_tipo_display()}'


class Aprendizagem(models.ModelPlus):
    CONCLUSAO = 1
    RESCISAO = 2
    ENCERRAMENTO_CHOICES = [[CONCLUSAO, 'Conclusão'], [RESCISAO, 'Rescisão']]

    MOTIVO_POR_TERMINO_CONTRATO = 1
    MOTIVO_CONTRATACAO_CONCEDENTE = 2
    MOTIVO_DESEMPENHO_INSUFICIENTE_INADAPTACAO = 3
    MOTIVO_RESCISAO_FALTA_DISCIPLINAR = 4
    MOTIVO_RESCISAO_AUSENCIA_INJUSTIFICADA = 5
    MOTIVO_RESCISAO_24_ANOS = 6
    MOTIVO_RESCISAO_A_PEDIDO_APRENDIZ = 7
    MOTIVO_CONCEDENTE_ENCERROU_ATIVIDADES = 8
    MOTIVACAO_DESLIGAMENTO_ENCERRAMENTO_CHOICHES = [
        [MOTIVO_POR_TERMINO_CONTRATO, 'Término do contrato.'],
        [MOTIVO_CONTRATACAO_CONCEDENTE, 'Contratação pela Concedente'],
        [MOTIVO_DESEMPENHO_INSUFICIENTE_INADAPTACAO, 'Rescisão por desempenho insuficiente ou inadaptação do aprendiz.'],
        [MOTIVO_RESCISAO_FALTA_DISCIPLINAR, 'Rescisão por falta disciplinar grave.'],
        [MOTIVO_RESCISAO_AUSENCIA_INJUSTIFICADA, 'Rescisão por ausência injustificada à escola que implique perda do ano letivo.'],
        [MOTIVO_RESCISAO_24_ANOS, 'Rescisão porque aprendiz atingiu 24 anos.'],
        [MOTIVO_RESCISAO_A_PEDIDO_APRENDIZ, 'Rescisão a pedido do aprendiz.'],
        [MOTIVO_CONCEDENTE_ENCERROU_ATIVIDADES, 'Concedente encerrou suas atividades.'],
    ]

    MENSAL = 1
    QUINZENAL = 2
    PERIODICIDADE_CHOICES = [[MENSAL, 'Mensal'], [QUINZENAL, 'Quinzenal']]

    NOME_MODELO_CONTRATO = 'Contrato de Aprendizagem'

    # Dados gerais
    aprendiz = models.ForeignKeyPlus(Aluno, verbose_name='Aprendiz')
    convenio = models.ForeignKeyPlus(Convenio, verbose_name='Convênio', null=True, blank=True)
    turno = models.ForeignKeyPlus(Turno, verbose_name='Turno', on_delete=models.CASCADE)
    empresa = models.ForeignKeyPlus(
        PessoaJuridica,
        verbose_name='Concedente',
        help_text='Para adicionar um concedente de aprendizagem, acesse o menu Administração -> Cadastros -> Pessoas Jurídicas.',
    )
    cidade = models.ForeignKeyPlus('edu.Cidade', verbose_name='Município', null=True, on_delete=models.CASCADE)
    logradouro = models.CharFieldPlus('Logradouro', null=True)
    numero = models.CharField('Nº', max_length=50, null=True)
    complemento = models.CharFieldPlus('Complemento', null=True, blank=True)
    bairro = models.CharFieldPlus('Bairro', null=True)
    cep = models.CharField('CEP', max_length=9, null=True)

    orientador = models.ForeignKeyPlus(Professor, verbose_name='Professor Orientador')

    # campos requisitados pela plataforma CNAP
    eh_contratacao_direta = models.BooleanField('Contratação direta?', null=True, blank=False)
    eh_modalidade_alternativa_de_cumprimento_de_cota = models.BooleanField('Modalidade alternativa de cumprimento de cota?', null=True, blank=False)
    o_estabelecimento_eh_de_prestacao_de_servico_a_terceiros = models.BooleanField(
        'Aprendizes do estabelecimento de prestação de serviços a terceiros? (Art. 344 da Portaria 671/2021)',
        null=True,
        blank=False,
    )
    aprendiz_contratado_mediante_centralizacao_de_cota = models.BooleanField(
        'Aprendiz contratado mediante centralização de cota? (Art. 345 da Portaria 671/2021)', null=True, blank=False
    )

    # remuneracao
    auxilio_transporte = models.DecimalFieldPlus(verbose_name='Auxílio Transporte (R$)', null=True, blank=True)
    outros_beneficios = models.DecimalFieldPlus(verbose_name='Outros Benefícios (R$)', null=True, blank=True)
    descricao_outros_beneficios = models.TextField('Descrição dos Outros Benefícios', null=True, blank=True)

    protocolo_cnap = models.CharFieldPlus('Protocolo de Aprovação do Curso - CNAP', max_length=50, null=False, blank=False)
    ocupacao = models.ForeignKeyPlus('comum.Ocupacao', verbose_name='Ocupação', null=True, blank=False, on_delete=models.CASCADE)

    # Documentação
    contrato_aprendizagem = models.FileFieldPlus(
        'Contrato de Aprendizagem',
        null=True,
        blank=True,
        max_length=255,
        upload_to='aprendizagem/contrato_aprendizagem',
        help_text='Arquivo digitalizado do contrato de aprendizagem.',
    )
    contrato_aprendizagem_documento_eletronico = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        verbose_name='Contrato de Aprendizagem (documento eletrônico)',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text='Documento eletrônico do contrato de aprendizagem.',
    )
    carteira_trabalho = models.FileFieldPlus(
        'Anotação na Carteira de Trabalho',
        blank=False,
        max_length=255,
        upload_to='aprendizagem/carteira_trabalho',
        help_text='Dever ser inserida comprovação de que o contrato foi anotado na carteira de trabalho do aprendiz.',
    )
    resumo_curso = models.FileFieldPlus(
        'Resumo do Curso de Aprendizagem',
        blank=True,
        max_length=255,
        upload_to='aprendizagem/resumo_curso',
        help_text='O resumo do curso encontra-se na plataforma: www.juventudeweb.mte.gov.br',
    )

    # Prática Profissional
    eh_utilizado_como_pratica_profissional = models.BooleanField('A aprendizagem será utilizada como prática profissional?')
    plano_atividades = models.FileFieldPlus(
        'Plano de Atividades',
        blank=True,
        max_length=255,
        upload_to='aprendizagem/planos_atividades',
        help_text='Plano de Atividades de acordo com a Resolução 25/2019, modelo disponível no endereço: http://portal.ifrn.edu.br/extensao/estagios-e-egressos',
    )

    # Empregado Monitor
    nome_monitor = models.CharFieldPlus('Nome', blank=False)
    telefone_monitor = models.CharFieldPlus('Telefone', null=True, blank=True)
    cargo_monitor = models.CharFieldPlus('Cargo', blank=False)
    email_monitor = models.CharFieldPlus('E-mail', blank=False, help_text='Este e-mail será importante para o envio da avaliação.')
    observacao = models.TextField('Observação', blank=True)
    monitor = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='aprendizagem_monitores',
        help_text='Só preencher esse campo se for utilizar a funcionalidade de Assinatura Eletrônica para relatórios de atividades.',
    )

    # Dados do contrato
    descricao_atividades = models.TextField(
        'Descrição as atividades da aprendizagem',
        null=True,
        blank=False,
        help_text='Estas atividades serão utilizadas para as avaliações da aprendizagem.',
    )
    data_inicio = models.DateFieldPlus('Data de início da aprendizagem', null=True, blank=False)
    data_prevista_encerramento = models.DateFieldPlus('Data de previsão para encerramento', null=True, blank=False)
    ch_teorica_semanal = models.IntegerFieldPlus('Carga-horária teórica semanal', null=True, blank=False)
    ch_pratica_semanal = models.IntegerFieldPlus('Carga-horária prática semanal', null=True, blank=False)

    # Módulo I
    modulo_1 = models.BooleanField('O aluno fará o módulo I?')

    # Módulo II
    modulo_2 = models.BooleanField('O aluno fará o módulo II?')

    # Módulo III
    modulo_3 = models.BooleanField('O aluno fará o módulo III?')

    # Módulo IV
    modulo_4 = models.BooleanField('O aluno fará o módulo IV?')

    # Encerramento: Dados do Encerramento
    encerramento_por = models.IntegerField('Encerramento por', choices=ENCERRAMENTO_CHOICES, null=True, blank=False)
    motivo_encerramento = models.IntegerField('Motivo do Encerramento', choices=MOTIVACAO_DESLIGAMENTO_ENCERRAMENTO_CHOICHES, null=True, blank=False)
    motivacao_rescisao = models.TextField(
        'Observações',
        null=True,
        blank=True,
        help_text='Inserir o motivo da rescisão, do encerramento com pendência ou outras informações relevantes.',
    )
    data_encerramento = models.DateFieldPlus('Data do Encerramento', null=True, blank=False)
    ch_final = models.IntegerField('Carga-Horária Prática Final', null=True, blank=False)

    # Encerramento: Documentação
    laudo_avaliacao = models.FileFieldPlus(
        'Laudo de Avaliação',
        blank=True,
        max_length=255,
        upload_to='aprendizagem/laudo_avaliacao',
        help_text='Documento necessário somente em caso de rescisão por desempenho insuficiente ou inadaptação do aprendiz.',
    )
    comprovante_encerramento = models.FileFieldPlus(
        'Comprovante de Encerramento',
        null=True,
        blank=False,
        max_length=255,
        upload_to='aprendizagem/comprovante_encerramento',
        help_text='Inserir a folha da carteira de trabalho que comprova o registro do encerramento do contrato com a sua respectiva data.',
    )
    codigo_verificador = models.TextField(default='')

    # Prazo para regularizar a matrícula
    prazo_final_regularizacao_matricula_irregular = models.DateFieldPlus('Prazo Final para Regularizar a Matrícula', null=True, blank=True)
    desvinculado_matricula_irregular = models.BooleanField(
        'Aluno Desvinculado por Matrícula Irregular', help_text='Selecione para o caso de abandono do aluno.', default=False
    )

    periodicidade_envio_relatorio_frequencia = models.PositiveIntegerFieldPlus(
        'Periodicidade de Envio do Relatório de Frequência', choices=PERIODICIDADE_CHOICES, null=True, blank=True
    )
    dia_inicio_apuracao_frequencia = models.PositiveIntegerFieldPlus(
        'Dia de Inicial do Período de Apuração',
        choices=[[dia, dia] for dia in range(1, 32, 1)],
        null=True,
        blank=True,
        help_text='Dia em cada mês a partir do qual a empresa contabiliza o ponto dos aprendizes num período mensal '
        'ou quinzenal, no qual serão apuradas suas faltas na instituição de ensino. Exemplo: Se for '
        'escolhida uma periodicidade Quinzenal e como Dia Inicial o dia 3, o primeiro período de '
        'apuração das faltas será do dia 3 ao dia 18 e o segundo período será do dia 19 ao dia 2 '
        'do mês seguinte. Como consequência, o relatório será enviado no dia 3 do mês seguinte',
    )

    inicio_periodo_frequencia_1 = models.PositiveIntegerFieldPlus(
        'Início do 1º Período', choices=[[dia, dia] for dia in range(1, 32, 1)], null=True, blank=True
    )
    fim_periodo_frequencia_1 = models.PositiveIntegerFieldPlus(
        'Fim do 1º Período', choices=[[dia, dia] for dia in range(1, 32, 1)], null=True, blank=True
    )
    inicio_periodo_frequencia_2 = models.PositiveIntegerFieldPlus(
        'Início do 2º Período (quinzenal)', choices=[[dia, dia] for dia in range(1, 32, 1)], null=True, blank=True
    )
    fim_periodo_frequencia_2 = models.PositiveIntegerFieldPlus(
        'Fim do 2º Período (quinzenal)',
        choices=[[dia, dia] for dia in range(1, 32, 1)],
        help_text='Preencher somente se o relatório for quinzenal.',
        null=True,
        blank=True,
    )
    emails_relatorio_frequencia = models.TextField(
        'E-mails para Envio do Relatório de Frequência',
        null=True,
        blank=True,
        help_text='Informe o(s) e-mail(s), separados por virgula, para o(s) quais será enviado o relatório de '
        'frequência do aprendiz. Não utilize espaços. Exemplo: rh@empresa.com.br, coordenador_estagio@ifrn.edu.br, '
        'monitor@empresa.com.br',
    )

    class Meta:
        verbose_name = 'Aprendizagem'
        verbose_name_plural = 'Aprendizagens'

    def __str__(self):
        return f'Aprendizagem do aluno {self.aprendiz} na concedente {self.empresa}'

    def get_absolute_url(self):
        return f'/estagios/aprendizagem/{self.pk}/'

    def clean(self):
        if self.eh_utilizado_como_pratica_profissional and not self.plano_atividades:
            raise ValidationError(
                {'plano_atividades': 'O plano de atividades é obrigatório no caso da aprendizagem ser utizada como prática profissional.'}
            )
        if hasattr(self, 'aprendiz'):
            if self.aprendiz and not self.aprendiz.matriz:
                raise ValidationError({'aprendiz': 'Aluno sem matriz não pode ser cadastrado.'})

            if not self.pk and self.aprendiz and self.aprendiz.situacao in get_situacoes_irregulares():
                raise ValidationError({'aprendiz': f'Aluno com situação {self.aprendiz.situacao.descricao} não pode estagiar.'})

            if self.aprendiz and self.aprendiz.curso_campus.modalidade not in Modalidade.objects.filter(
                id__in=Modalidade.modalidades_que_fazem_estagio()
            ):
                raise ValidationError(
                    {
                        'aprendiz': f'Este aluno é da modalidade {self.aprendiz.curso_campus.modalidade.descricao}. Somente alunos das modalidades Licenciatura, Engenharia, Integrado, Integrado Eja, Subsequente e Tecnologia podem participar de programa de aprendizagem.'
                    }
                )

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.codigo_verificador:
            self.codigo_verificador = hashlib.sha1(f'{self.orientador.pk}{datetime.datetime.now()}{settings.SECRET_KEY}'.encode()).hexdigest()
        super().save()
        if not Aprendizagem.cadastra_modulos_manualmente(self):
            self.organizar_modulos_por_semestres()

    @cached_property
    def _diretores_academicos_responsaveis(self):
        return set(get_diretores_academicos(self.aprendiz))

    def eh_diretor_academico(self, user):
        return user in self._diretores_academicos_responsaveis

    def eh_coordenador_de_extensao(self, user):
        campus_usuario = get_uo(user)
        return in_group(user, 'Coordenador de Extensão') and campus_usuario == self.aprendiz.campus

    def eh_aprendiz(self, user):
        return usuario_possui_cadastro(user) and self.aprendiz == user.get_relacionamento()

    def eh_orientador(self, user):
        return usuario_possui_cadastro(user) and self.orientador and self.orientador.get_vinculo() == user.get_vinculo()

    def eh_monitor(self, user):
        return usuario_possui_cadastro(user) and self.monitor and self.monitor == user.get_vinculo()

    @classmethod
    def cadastra_modulos_manualmente(cls, aprendizagem):
        """
        Verifica se a aprendizagem requer o cadastro manual dos módulos, ou se eles serão
        gerados automaticamente pelo sistema.

        Se `aprendizagem` não for informada ou não existir, o método verificará a Configuração:
        app = 'estagios', chave = 'cadastrar_modulos_aprendizagem_manualmente'.
        """
        if aprendizagem and aprendizagem.pk:
            return not aprendizagem.descricao_atividades

        return bool(Configuracao.get_valor_por_chave('estagios', 'cadastrar_modulos_aprendizagem_manualmente'))

    @property
    def nomenclatura_periodo(self):
        return 'Semestre' if self.descricao_atividades else 'Módulo'

    def get_periodos(self, meses=6):
        data_fim = self.data_prevista_encerramento
        periodos = []
        inicio_prox_periodo = self.data_inicio
        while True:
            fim_prox_periodo = (inicio_prox_periodo + relativedelta(months=meses)) - datetime.timedelta(1)
            if fim_prox_periodo > data_fim:
                fim_prox_periodo = data_fim
            if inicio_prox_periodo != fim_prox_periodo:
                periodos.append({'inicio': inicio_prox_periodo, 'fim': fim_prox_periodo})
            if fim_prox_periodo != data_fim:
                inicio_prox_periodo = fim_prox_periodo + datetime.timedelta(1)
            else:
                break
        if len(periodos) == 0:
            periodos.append({'inicio': inicio_prox_periodo, 'fim': fim_prox_periodo})
        return periodos

    def organizar_modulos_por_semestres(self):
        if not Aprendizagem.cadastra_modulos_manualmente(self):
            periodos = self.get_periodos(meses=6)

            # garantindo que haverá, no máximo, 4 períodos, para manter compatibilidade com Módulos
            if len(periodos) > 4:
                fim_ultimo_periodo = periodos[-1].get('fim')
                periodos[3]['fim'] = fim_ultimo_periodo
                periodos = periodos[:4]

            tipos_de_modulos = {
                1: ModuloAprendizagem.MODULO_I,
                2: ModuloAprendizagem.MODULO_II,
                3: ModuloAprendizagem.MODULO_III,
                4: ModuloAprendizagem.MODULO_IV,
            }

            # cria/atualiza dados dos semestres
            for i, periodo in enumerate(periodos, start=1):
                tipo_modulo = tipos_de_modulos.get(i)

                modulo = self.moduloaprendizagem_set.filter(tipo_modulo=tipo_modulo).first()
                if not modulo:
                    modulo = ModuloAprendizagem()
                    modulo.aprendizagem = self
                    modulo.tipo_modulo = tipo_modulo
                modulo.atividades = self.descricao_atividades
                modulo.inicio = periodo.get('inicio')
                modulo.fim = periodo.get('fim')
                modulo.ch_teorica_semanal = self.ch_teorica_semanal
                modulo.ch_pratica_semanal = self.ch_pratica_semanal
                modulo.save()

    def pode_anexar_arquivos(self, user=None):
        if self.data_encerramento:
            return False
        if user:
            return in_group(user, 'Coordenador de Estágio Sistêmico,Coordenador de Estágio,Coordenador de Extensão')

        return False

    def notificar_professores_diarios(self, user=None):
        professores = Professor.objects.filter(
            professordiario__diario__matriculadiario__matricula_periodo__pk=self.aprendiz.get_ultima_matricula_periodo().pk,
            professordiario__diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
        ).distinct()
        emails_professores = professores.values_list('vinculo__user__email', flat=True)
        titulo = '[SUAP] Notificação de Aluno Aprendiz'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_professores_diarios.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
            },
        )
        vinculos = []
        for professor in professores:
            vinculos.append(professor.vinculo)

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)

        notificacao = NotificacaoAprendizagem(
            aprendizagem=self,
            data=datetime.datetime.now(),
            tipo=NotificacaoAprendizagem.NOTIFICACAO_INICIAL_PROFESSORES_DIARIOS,
            notificador=user,
            email_destinatario=', '.join(emails_professores),
            mensagem_enviada=f'{titulo}<br/>{mensagem}',
        )
        notificacao.save()

    def get_campus(self):
        return f'{self.aprendiz.curso_campus.diretoria.setor.uo}'

    get_campus.admin_order_field = 'aprendiz__curso_campus__diretoria__setor__uo'
    get_campus.short_description = 'Campus'

    def get_situacao_aluno(self):
        return f'{self.aprendiz.situacao}'

    get_situacao_aluno.admin_order_field = 'aprendiz__situacao__descricao'
    get_situacao_aluno.short_description = 'Situação do Aprendiz'

    def get_situacao_ultima_matricula_periodo(self):
        return f'{self.aprendiz.get_ultima_matricula_periodo().situacao}'

    get_situacao_ultima_matricula_periodo.admin_order_field = 'aprendiz__matriculaperiodo__situacao__descricao'
    get_situacao_ultima_matricula_periodo.short_description = 'Situação da Matrícula no Período'

    def get_email_aprendiz(self):
        return self.aprendiz.email_notificacao

    def gerar_documento_eletronico_do_contrato(self, usuario_criacao):
        try:
            modelo = ModeloDocumento.objects.get(nome=self.NOME_MODELO_CONTRATO)
        except ModeloDocumento.DoesNotExist:
            raise Exception(f'Não existe modelo de documento texto com nome "{self.NOME_MODELO_CONTRATO}".')

        instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
        setor_dono = get_setor(usuario_criacao)
        uo = setor_dono.uo

        # Monitor
        monitor_nome = self.monitor.nome if self.monitor else self.nome_monitor

        # Telefone Orientador
        if self.orientador.vinculo.pessoa.telefones:
            telefone_orientador = self.orientador.vinculo.pessoa.telefones
        else:
            telefone_orientador = self.orientador.vinculo.setor.telefones

        duracao_aprendizagem = relativedelta(self.data_prevista_encerramento, self.data_inicio)

        vinculo_empresa = self.empresa.get_vinculo()

        def to_str_or_empty(s):
            if s is not None:
                return str(s)
            return ''

        variaveis = get_variaveis(
            documento_identificador=None,
            estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
            usuario=usuario_criacao,
            setor_dono=setor_dono,
        )

        # Tags do modelo
        variaveis.update(
            {
                # Instituição
                'instituicao_nome': to_str_or_empty(instituicao),
                'campus_endereco': f'{uo.endereco}, {uo.numero}',
                'campus_bairro': to_str_or_empty(uo.bairro),
                'campus_municipio': to_str_or_empty(uo.municipio.nome),
                'campus_uf': to_str_or_empty(uo.municipio.uf),
                'campus_cep': to_str_or_empty(uo.cep),
                'campus_cnpj': to_str_or_empty(uo.cnpj),
                'campus_telefone': to_str_or_empty(uo.telefone),
                # Orientador
                'orientador_nome': to_str_or_empty(self.orientador.vinculo.pessoa.nome),
                'orientador_telefone': telefone_orientador,
                'orientador_email': to_str_or_empty(self.orientador.vinculo.email_notificacao),
                # Aprendiz
                'aprendiz_nome': to_str_or_empty(self.aprendiz.pessoa_fisica.nome),
                'aprendiz_cpf': to_str_or_empty(self.aprendiz.pessoa_fisica.cpf),
                'aprendiz_data_nascimento': self.aprendiz.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y'),
                'aprendiz_rg': to_str_or_empty(self.aprendiz.numero_rg),
                'aprendiz_orgaoexpedidor_rg': to_str_or_empty(self.aprendiz.orgao_emissao_rg),
                'aprendiz_numero_ctps': to_str_or_empty(self.aprendiz.pessoa_fisica.ctps_numero),
                'aprendiz_endereco': f'{self.aprendiz.logradouro}, {self.aprendiz.numero}. {self.aprendiz.complemento}'.strip(),
                'aprendiz_bairro': to_str_or_empty(self.aprendiz.bairro),
                'aprendiz_uf': to_str_or_empty(self.aprendiz.cidade.estado.get_sigla()),
                'aprendiz_cidade': to_str_or_empty(self.aprendiz.cidade),
                'aprendiz_cep': to_str_or_empty(self.aprendiz.cep),
                'aprendiz_telefone': to_str_or_empty(self.aprendiz.telefone_principal),
                'aprendiz_email': to_str_or_empty(self.aprendiz.email_notificacao),
                'aprendiz_curso': to_str_or_empty(self.aprendiz.curso_campus.descricao_historico),
                'aprendiz_periodo_ano': f'{self.aprendiz.periodo_atual}º {"ANO" if self.aprendiz.curso_campus.is_anual() else "PERÍODO"}',
                'aprendiz_nivel': to_str_or_empty(self.aprendiz.matriz.nivel_ensino),
                'aprendiz_tem_necessidade_especial': 'Sim' if self.aprendiz.is_pcd() else 'Não',
                # Concedente - dados básicos
                'concedente_razao_social': to_str_or_empty(self.empresa.nome),
                'concedente_nome_fantasia': to_str_or_empty(self.empresa.nome_fantasia) if self.empresa.eh_pessoa_juridica else self.empresa.nome,
                'concedente_cnpj_cpf': to_str_or_empty(self.empresa.get_cpf_ou_cnpj()),
                'concedente_nome_representante': to_str_or_empty(self.empresa.nome_representante_legal) if self.empresa.eh_pessoa_juridica else '',
                'concedente_ramo_atividade': to_str_or_empty(self.empresa.ramo_atividade) if self.empresa.eh_pessoa_juridica else '',
                # Concedente - endereço e contato
                'concedente_uf': to_str_or_empty(self.cidade.estado.get_sigla()),
                'concedente_cidade': to_str_or_empty(self.cidade),
                'concedente_endereco': f'{self.logradouro}, {self.numero}. {self.complemento}'.strip(),
                'concedente_bairro': to_str_or_empty(self.bairro),
                'concedente_cep': to_str_or_empty(self.cep),
                'concedente_email': to_str_or_empty(vinculo_empresa.email_notificacao if vinculo_empresa else ''),
                'concedente_telefone': to_str_or_empty(self.empresa.telefones),
                # Monitor
                'monitor_nome': monitor_nome,
                'monitor_cargo': to_str_or_empty(self.cargo_monitor),
                'monitor_email': to_str_or_empty(self.email_monitor),
                'monitor_telefone': to_str_or_empty(self.telefone_monitor),
                # Outras variáveis
                'ocupacao': to_str_or_empty(self.ocupacao.descricao),
                'cbo': to_str_or_empty(self.ocupacao.codigo),
                'data_inicio': self.data_inicio.strftime('%d/%m/%Y'),
                'data_prevista_encerramento': self.data_prevista_encerramento.strftime('%d/%m/%Y'),
                'duracao_meses': duracao_aprendizagem.months,
                'jornada_semanal': to_str_or_empty(self.ch_teorica_semanal + self.ch_pratica_semanal),
                'cumpre_cota_alternativa': 'Sim' if self.eh_modalidade_alternativa_de_cumprimento_de_cota else 'Não',
                'centraliza_atividades_praticas': 'Sim' if self.aprendiz_contratado_mediante_centralizacao_de_cota else 'Não',
                'prestacao_de_servicos_a_terceiros': 'Sim' if self.o_estabelecimento_eh_de_prestacao_de_servico_a_terceiros else 'Não',
                'descricao_atividades': to_str_or_empty(self.get_descricao_atividades.replace('\n', '<br>')),
            }
        )

        try:
            documento = DocumentoTexto.adicionar_documento_texto(
                usuario=usuario_criacao,
                setor_dono=setor_dono,
                assunto=f'Contrato da {self}',
                modelo=modelo,
                nivel_acesso=Documento.NIVEL_ACESSO_RESTRITO,
                hipotese_legal=HipoteseLegal.objects.get(descricao='Informação Pessoal'),
                variaveis=variaveis,
            )

            self.contrato_aprendizagem_documento_eletronico = documento
            self.save()

            return documento
        except Exception as e:
            raise e

    @property
    def get_descricao_atividades(self):
        descricao_atividades = self.descricao_atividades or ''
        if not descricao_atividades:
            for modulo in self.moduloaprendizagem_set.order_by('tipo_modulo'):
                descricao_atividades += f'{modulo.get_tipo_modulo_display().upper()}:\n{modulo.atividades}\n'
        return descricao_atividades.strip()

    def enviar_email_empregado_monitor_recem_cadastrado(self, user=None):
        titulo = '[SUAP] Cadastro como Empregado Monitor de Aprendizagem'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_cadastrada.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'email_orientador': self.orientador.vinculo.email_notificacao,
                'nome_monitor': self.nome_monitor,
                'url_portal': Configuracao.get_valor_por_chave('comum', 'url_portal'),
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_aprendizagem'),
                'versao': 'monitor',
            },
        )

        send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.email_monitor])
        notificao = NotificacaoAprendizagem(
            aprendizagem=self,
            data=datetime.datetime.now(),
            tipo=NotificacaoAprendizagem.NOTIFICACAO_INICIAL,
            notificador=user,
            email_destinatario=self.email_monitor,
            mensagem_enviada=f'{titulo}<br/>{mensagem}',
        )
        notificao.save()

    def enviar_email_orientador_recem_cadastrado(self, user=None):
        titulo = '[SUAP] Cadastro como Orientador de Aprendizagem'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_cadastrada.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'nome_orientador': self.orientador.get_nome(),
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_aprendizagem'),
                'versao': 'orientador',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_INICIAL,
                notificador=user,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def enviar_email_aprendiz_recem_cadastrado(self, user=None):
        titulo = '[SUAP] Cadastro de Aprendizagem'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_cadastrada.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'nome_orientador': self.orientador.get_nome(),
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_aprendizagem'),
                'versao': 'aprendiz',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aprendiz.get_vinculo()])
        email_aprendiz = self.get_email_aprendiz()
        if email_aprendiz:
            notificao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_INICIAL,
                notificador=user,
                email_destinatario=email_aprendiz,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    @property
    def get_relatorios_aprendiz(self):
        return RelatorioModuloAprendizagem.objects.filter(modulo_aprendizagem__aprendizagem=self, eh_relatorio_do_empregado_monitor=False).order_by(
            'modulo_aprendizagem__inicio'
        )

    @property
    def get_relatorios_monitor(self):
        return RelatorioModuloAprendizagem.objects.filter(modulo_aprendizagem__aprendizagem=self, eh_relatorio_do_empregado_monitor=True).order_by(
            'modulo_aprendizagem__inicio'
        )

    @property
    def usa_assinatura_eletronica_relatorios(self):
        return RelatorioModuloAprendizagem.objects.filter(modulo_aprendizagem__aprendizagem=self, relatorio='').exists()

    def get_sugestao_ch_final(self):
        dias_modulo = 0
        ch_sugerida = 0
        for modulo in self.moduloaprendizagem_set.all():
            dias_modulo = numpy.busday_count(modulo.inicio, modulo.fim + datetime.timedelta(days=1))
            ch_sugerida = ch_sugerida + dias_modulo * (modulo.ch_pratica_semanal / 5.0)

        return (
            f'Para cada {self.nomenclatura_periodo.lower()} desta aprendizagem, dada a data cadastrada de início e a data '
            'prevista para o fim, considerando que a carga horária semanal é distribuída igualmente em todos os dias de '
            'trabalho, considerando-se dias de trabalho apenas o intervalo de segunda a sexta, estima-se uma carga horária '
            f'prática de {format_(ch_sugerida)} horas. Desse total não são excluídos feriados e nem outras possíveis interrupções das '
            'atividades na concedente.'
        )

    def ha_pendencia_de_visita(self, data_considerada=None):
        if not data_considerada:
            data_considerada = datetime.date.today()

        if self.data_encerramento:
            return False
        for modulo in self.moduloaprendizagem_set.all():
            if (
                not modulo.visitaaprendizagem_set.exists()
                and not modulo.justificativavisitamoduloaprendizagem_set.exists()
                and modulo.fim <= data_considerada
            ):
                return True
        return False

    def ha_pendencia_relatorio_monitor(self, data_considerada=None):
        if not data_considerada:
            data_considerada = datetime.date.today()

        if self.data_encerramento:
            return False
        return any(not modulo.tem_relatorio_monitor() and modulo.fim <= data_considerada for modulo in self.moduloaprendizagem_set.all())

    def ha_pendencia_relatorio_aprendiz(self, data_considerada=None):
        if not data_considerada:
            data_considerada = datetime.date.today()

        if self.data_encerramento:
            return False
        return any(not modulo.tem_relatorio_aprendiz() and modulo.fim <= data_considerada for modulo in self.moduloaprendizagem_set.all())

    @property
    def qtd_relatorios_aprendiz_pendentes(self):
        if self.data_encerramento:
            return 0
        qtd = 0
        for modulo in self.moduloaprendizagem_set.all():
            if not modulo.tem_relatorio_aprendiz() and modulo.fim < datetime.date.today():
                qtd += 1
        return qtd

    def resumo_pendencias(self):
        if self.data_encerramento:
            retorno = 'Encerrado'

        pendencias = []
        if self.ha_pendencia_relatorio_aprendiz():
            pendencias.append('de relatório do aprendiz')
        if self.ha_pendencia_relatorio_monitor():
            pendencias.append('de relatório do monitor')
        if self.usa_assinatura_eletronica_relatorios:
            qs_assinaturas_pendentes = RelatorioModuloAprendizagem.objects.filter(
                Q(modulo_aprendizagem__aprendizagem=self),
                Q(relatorio=''),
                Q(assinatura_aprendiz=None) | Q(assinatura_orientador=None) | Q(assinatura_monitor=None),
            )
            if qs_assinaturas_pendentes.filter(eh_relatorio_do_empregado_monitor=True).exists():
                pendencias.append('de assinatura de relatório do empregado monitor')
            if qs_assinaturas_pendentes.filter(eh_relatorio_do_empregado_monitor=False).exists():
                pendencias.append('de assinatura de relatório do aprendiz')
        if pendencias:
            pendencias = ', '.join(pendencias)
            retorno = f'Pendências: {pendencias}'
        else:
            retorno = 'Sem pendências'
        return mark_safe(retorno)

    resumo_pendencias.short_description = 'Resumo de Pendências'

    def verificar_pendencias(self):
        if not self.data_encerramento:
            self.notificar_pendencia_avaliacao_modulo_monitor()
            self.notificar_pendencia_avaliacao_modulo_aprendiz()

    def notificar(
        self,
        cadastro_rel_atividades=True,
        assinatura_rel_atividades=True,
        revisao_rel_atividades=True,
        matricula_irregular=True,
        relatorio_frequencia=True,
    ):
        if not self.data_encerramento:
            if cadastro_rel_atividades:
                self.notificar_pendencia_avaliacao_modulo_monitor(deve_notificar_se_pendente=True)
                self.notificar_pendencia_avaliacao_modulo_aprendiz(deve_notificar_se_pendente=True)
            if assinatura_rel_atividades:
                self.notificar_pendencias_assinatura_relatorios_modulos()
            if revisao_rel_atividades:
                self.notificar_orientador_divergencia_relatorios_modulo_aprendizagem()
                self.notificar_orientador_necessidade_revisao()
            if matricula_irregular:
                self.verificar_matricula_irregular()
            if relatorio_frequencia:
                self.verificar_envio_relatorio_frequencia()

    def verificar_visitas_pendentes(self, deve_notificar_se_pendente=False, user=None):
        hoje = datetime.date.today()
        for modulo in self.moduloaprendizagem_set.all():
            if not modulo.visitaaprendizagem_set.exists() and modulo.inicio < hoje:
                url_aprendizagem = f'{settings.SITE_URL}{self.get_absolute_url()}'
                url_manuais = Configuracao.get_valor_por_chave('estagios', 'url_manuais_aprendizagem')
                if self.deve_enviar_primeira_notificacao_de_visita(modulo) or self.deve_enviar_segunda_notificacao_de_visita(modulo):
                    titulo = '[SUAP] Lembrete de Visita de Orientação de Aprendizagem'
                    mensagem = render_to_string(
                        template_name='notificacoes/aprendizagem_visita_pendente.html',
                        context={
                            'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                            'matricula_aprendiz': self.aprendiz.matricula,
                            'data_inicio': self.data_inicio,
                            'data_prevista_encerramento': self.data_prevista_encerramento,
                            'modulo': modulo,
                            'url_aprendizagem': url_aprendizagem,
                            'url_manuais': url_manuais,
                            'versao': 'lembrete_antecipado',
                        },
                    )

                    send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
                    if self.orientador.vinculo.user.email:
                        notificacao = NotificacaoAprendizagem(
                            aprendizagem=self,
                            data=datetime.datetime.now(),
                            tipo=NotificacaoAprendizagem.NOTIFICACAO_VISITA,
                            notificador=user,
                            email_destinatario=self.orientador.vinculo.user.email,
                            mensagem_enviada=f'{titulo}<br/>{mensagem}',
                        )
                        notificacao.save()
                        modulo_notificado = ModuloComPendenciaNotificado(modulo=modulo, notificacao=notificacao)
                        modulo_notificado.save()
                elif self.deve_enviar_notificacao_apos_fim_periodo(modulo) or (modulo.fim < hoje and deve_notificar_se_pendente):
                    titulo = '[SUAP] Pendência de Registro de Visita'
                    mensagem = render_to_string(
                        template_name='notificacoes/aprendizagem_visita_pendente.html',
                        context={
                            'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                            'matricula_aprendiz': self.aprendiz.matricula,
                            'data_inicio': self.data_inicio,
                            'data_prevista_encerramento': self.data_prevista_encerramento,
                            'modulo': modulo,
                            'url_aprendizagem': url_aprendizagem,
                            'versao': 'prazo_expirado',
                        },
                    )

                    send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
                    if self.orientador.vinculo.user.email:
                        notificacao = NotificacaoAprendizagem(
                            aprendizagem=self,
                            data=datetime.datetime.now(),
                            tipo=NotificacaoAprendizagem.NOTIFICACAO_VISITA,
                            notificador=user,
                            email_destinatario=self.orientador.vinculo.user.email,
                            mensagem_enviada=f'{titulo}<br/>{mensagem}',
                        )
                        notificacao.save()
                        modulo_notificado = ModuloComPendenciaNotificado(modulo=modulo, notificacao=notificacao)
                        modulo_notificado.save()

    def deve_enviar_primeira_notificacao_de_visita(self, modulo):
        def dia_inicial_para_envio(modulo):
            return modulo.inicio + (modulo.fim - modulo.inicio) / 3

        def dia_final_para_envio(modulo):
            return modulo.inicio + 2 * (modulo.fim - modulo.inicio) / 3 - relativedelta(days=1)

        return bool(
            datetime.date.today() >= dia_inicial_para_envio(modulo)
            and datetime.date.today() < dia_final_para_envio(modulo)
            and not ModuloComPendenciaNotificado.objects.filter(
                notificacao__aprendizagem=self,
                modulo=modulo,
                notificacao__data__date__gte=dia_inicial_para_envio(modulo),
                notificacao__data__date__lt=dia_final_para_envio(modulo),
            ).exists()
        )

    def deve_enviar_segunda_notificacao_de_visita(self, modulo):
        def dia_inicial_para_envio(modulo):
            return modulo.inicio + 2 * (modulo.fim - modulo.inicio) / 3

        def dia_final_para_envio(modulo):
            return modulo.fim

        return bool(
            datetime.date.today() >= dia_inicial_para_envio(modulo)
            and datetime.date.today() <= dia_final_para_envio(modulo)
            and not ModuloComPendenciaNotificado.objects.filter(
                notificacao__aprendizagem=self,
                modulo=modulo,
                notificacao__data__date__gte=dia_inicial_para_envio(modulo),
                notificacao__data__date__lte=dia_final_para_envio(modulo),
            ).exists()
        )

    def deve_enviar_notificacao_apos_fim_periodo(self, modulo):
        return bool(
            datetime.date.today() > modulo.fim
            and not ModuloComPendenciaNotificado.objects.filter(
                notificacao__aprendizagem=self, modulo=modulo, notificacao__data__date__gt=datetime.date.today() + relativedelta(days=-10)
            ).exists()
        )

    def notificar_pendencia_avaliacao_modulo_monitor(self, deve_notificar_se_pendente=False, user=None):
        hoje = datetime.date.today()
        for modulo in self.moduloaprendizagem_set.all():
            if (
                not modulo.tem_relatorio_monitor()
                and modulo.fim < hoje
                and (
                    deve_notificar_se_pendente
                    or not ModuloComPendenciaNotificado.objects.filter(
                        modulo=modulo,
                        notificacao__aprendizagem=self,
                        notificacao__tipo=NotificacaoAprendizagem.NOTIFICACAO_RELATORIO_MONITOR,
                        notificacao__data__date__gte=datetime.date.today() + relativedelta(days=-10),
                    ).exists()
                )
            ):
                url_submissao_relatorio = (
                    f'{settings.SITE_URL}/estagios/avaliar_aprendizagem_monitor/'
                    f'?matricula={self.aprendiz.matricula}'
                    f'&codigo_verificador={self.codigo_verificador[0:6]}'
                    f'&email_monitor={self.email_monitor}'
                    f'&inicio={format_(modulo.inicio)}&fim={format_(modulo.fim)}'
                )
                titulo = '[SUAP] Pendência de Avaliação de Aprendiz sob sua Monitoria'
                mensagem = render_to_string(
                    template_name='notificacoes/aprendizagem_rel_atividades_pendente.html',
                    context={
                        'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                        'matricula_aprendiz': self.aprendiz.matricula,
                        'data_inicio': self.data_inicio,
                        'modulo': modulo,
                        'data_inicio_envio': modulo.fim + datetime.timedelta(1),
                        'url_submissao_relatorio': url_submissao_relatorio,
                        'url_modelos_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_aprendizagem'),
                        'versao': 'monitor',
                    },
                )

                send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.email_monitor])
                notificacao = NotificacaoAprendizagem(
                    aprendizagem=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoAprendizagem.NOTIFICACAO_RELATORIO_MONITOR,
                    notificador=user,
                    email_destinatario=self.email_monitor,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()
                modulo_notificado = ModuloComPendenciaNotificado(modulo=modulo, notificacao=notificacao)
                modulo_notificado.save()

    def notificar_pendencia_avaliacao_modulo_aprendiz(self, deve_notificar_se_pendente=False, user=None):
        hoje = datetime.date.today()
        for modulo in self.moduloaprendizagem_set.all():
            if (
                not modulo.tem_relatorio_aprendiz()
                and modulo.fim < hoje
                and (
                    deve_notificar_se_pendente
                    or not ModuloComPendenciaNotificado.objects.filter(
                        modulo=modulo,
                        notificacao__aprendizagem=self,
                        notificacao__tipo=NotificacaoAprendizagem.NOTIFICACAO_RELATORIO_APRENDIZ,
                        notificacao__data__date__gte=datetime.date.today() + relativedelta(days=-10),
                    ).exists()
                )
            ):
                url_aprendizagem = f'{settings.SITE_URL}{self.get_absolute_url()}'
                titulo = '[SUAP] Pendência de Envio de Relatório de Atividades de Aprendizagem'
                mensagem = render_to_string(
                    template_name='notificacoes/aprendizagem_rel_atividades_pendente.html',
                    context={
                        'modulo': modulo,
                        'data_inicio_envio': modulo.fim + datetime.timedelta(1),
                        'url_aprendizagem': url_aprendizagem,
                        'url_modelos_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_aprendizagem'),
                        'versao': 'aprendiz',
                    },
                )

                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aprendiz.get_vinculo()])
                if self.get_email_aprendiz():
                    notificacao = NotificacaoAprendizagem(
                        aprendizagem=self,
                        data=datetime.datetime.now(),
                        tipo=NotificacaoAprendizagem.NOTIFICACAO_RELATORIO_APRENDIZ,
                        notificador=user,
                        email_destinatario=self.get_email_aprendiz(),
                        mensagem_enviada=f'{titulo}<br/>{mensagem}',
                    )
                    notificacao.save()
                    modulo_notificado = ModuloComPendenciaNotificado(modulo=modulo, notificacao=notificacao)
                    modulo_notificado.save()

    def pode_cadastrar_relatorio_aprendiz(self, user):
        return (
            self.eh_aprendiz(user)
            or self.eh_orientador(user)
            or tem_permissao_de_coordenador(user, campus=self.aprendiz.campus)
            or in_group(user, 'estagios Administrador')
        )

    def pode_cadastrar_relatorio_monitor(self, user):
        return (
            self.eh_monitor(user)
            or self.eh_orientador(user)
            or tem_permissao_de_coordenador(user, campus=self.aprendiz.campus)
            or in_group(user, 'estagios Administrador')
        )

    def pode_justificar_decurso_prazo_visita(self, user, modulo):
        return (
            not self.data_encerramento
            and modulo.esta_encerrado
            and not modulo.tem_visitas()
            and (self.eh_orientador(user) or in_group(user, 'estagios Administrador') or tem_permissao_de_coordenador(user, self.aprendiz.campus))
        )

    def get_aditivo(self):
        lista = ['<ul>']
        for aditivo in self.aditivocontratualaprendizagem_set.all():
            lista.append(f'<li>{aditivo}</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_aditivo.short_description = 'Aditivos Contratuais'

    def get_inicio_vigencia_ultimo_aditivo(self):
        ultimo_aditivo = self.aditivocontratualaprendizagem_set.last()
        return ultimo_aditivo and ultimo_aditivo.inicio_vigencia or None

    def get_modulo_1(self):
        if self.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_I).exists():
            return self.moduloaprendizagem_set.get(tipo_modulo=ModuloAprendizagem.MODULO_I)
        else:
            return None

    def get_modulo_2(self):
        if self.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_II).exists():
            return self.moduloaprendizagem_set.get(tipo_modulo=ModuloAprendizagem.MODULO_II)
        else:
            return None

    def get_modulo_3(self):
        if self.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_III).exists():
            return self.moduloaprendizagem_set.get(tipo_modulo=ModuloAprendizagem.MODULO_III)
        else:
            return None

    def get_modulo_4(self):
        if self.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_IV).exists():
            return self.moduloaprendizagem_set.get(tipo_modulo=ModuloAprendizagem.MODULO_IV)
        else:
            return None

    def get_media_notas_avaliacoes_empregado_monitor(self):
        return RelatorioModuloAprendizagem.objects.filter(modulo_aprendizagem__aprendizagem=self, eh_relatorio_do_empregado_monitor=True).aggregate(
            Avg('nota_aprendiz')
        )['nota_aprendiz__avg']

    def get_periodo_duracao(self):
        if self.data_encerramento:
            return [self.data_inicio, self.data_encerramento]
        else:
            return [self.data_inicio, self.data_prevista_encerramento]

    def mostrar_botao_cancelar_encerramento(self):
        return (
            self.data_encerramento
            and not SolicitacaoCancelamentoEncerramentoEstagio.objects.filter(
                aprendizagem=self, situacao=SolicitacaoCancelamentoEncerramentoEstagio.AGUARDANDO_RESPOSTA
            ).exists()
        )

    def ha_solicitacao_cancelamento_encerramento_aguardando_resposta(self):
        return SolicitacaoCancelamentoEncerramentoEstagio.objects.filter(
            aprendizagem=self, situacao=SolicitacaoCancelamentoEncerramentoEstagio.AGUARDANDO_RESPOSTA
        ).exists()

    def verificar_matricula_irregular(self):
        # se ocorreu matrícula irregular por parte de um aluno
        if self.aprendiz.situacao in get_situacoes_irregulares() and not self.prazo_final_regularizacao_matricula_irregular:
            self.prazo_final_regularizacao_matricula_irregular = datetime.date.today() + relativedelta(days=7)
            self.save()
            self.notificar_empregado_monitor_matricula_irregular()
            self.notificar_aluno_matricula_irregular()
            self.notificar_orientador_aluno_matricula_irregular()
            self.notificar_coordenador_aluno_matricula_irregular()
            self.notificar_coordenacao_extensao_aluno_matricula_irregular()
        # se foi dado prazo e o aluno regularizou a matrícula
        if self.aprendiz.situacao not in get_situacoes_irregulares() and self.prazo_final_regularizacao_matricula_irregular:
            self.prazo_final_regularizacao_matricula_irregular = None
            self.save()
            self.notificar_empregado_monitor_matricula_regularizada()
        # se a situacao irregular persistiu por mais de 7 dias
        if (
            self.aprendiz.situacao in get_situacoes_irregulares()
            and self.prazo_final_regularizacao_matricula_irregular
            and self.prazo_final_regularizacao_matricula_irregular < datetime.date.today()
            and not self.notificacaoaprendizagem_set.filter(tipo=NotificacaoAprendizagem.NOTIFICACAO_INTERRUPCAO).exists()
        ):
            self.notificar_aluno_interrupcao()
            self.notificar_empregado_monitor_sobre_interrupcao_aprendizagem()
            self.notificar_orientador_interrupcao()

    def notificar_aluno_matricula_irregular(self):
        instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        titulo = '[SUAP] Notificação de Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_matricula_irregular.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'curso': self.aprendiz.curso_campus,
                'data_prevista_encerramento': self.data_prevista_encerramento,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'instituicao_sigla': instituicao_sigla,
                'versao': 'aprendiz',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aprendiz.get_vinculo()])
        email_aluno = self.get_email_aprendiz()
        if email_aluno:
            notificao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def notificar_empregado_monitor_matricula_irregular(self):
        coordenadores = get_coordenadores_estagio(self.aprendiz)
        emails_coordenadores = get_coordenadores_emails(coordenadores)
        titulo = 'Notificação de Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_matricula_irregular.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'nome_monitor': self.nome_monitor,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'emails_coordenadores': emails_coordenadores,
                'versao': 'monitor',
            },
        )

        email_monitor = self.email_monitor
        if email_monitor:
            send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [email_monitor])
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=email_monitor,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_empregado_monitor_matricula_regularizada(self):
        titulo = 'Notificação de Matrícula Regularizada'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_matricula_regularizada.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'nome_monitor': self.nome_monitor,
                'data_prevista_encerramento': self.data_prevista_encerramento,
                'nomenclatura_periodo': self.nomenclatura_periodo,
            },
        )

        email_monitor = self.email_monitor
        if email_monitor:
            send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [email_monitor])
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=email_monitor,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_coordenador_aluno_matricula_irregular(self):
        titulo = '[SUAP] Notificação de Aluno de Curso sob sua Coordenação com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_matricula_irregular.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'nome_coordenador': self.aprendiz.curso_campus.coordenador.nome,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'versao': 'coordenador_do_curso',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aprendiz.curso_campus.coordenador])
        if self.aprendiz.curso_campus.coordenador.user.email:
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.aprendiz.curso_campus.coordenador.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_orientador_aluno_matricula_irregular(self):
        titulo = '[SUAP] Notificação de Orientando com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_matricula_irregular.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'nome_orientador': self.orientador.get_nome(),
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'versao': 'orientador',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_coordenacao_extensao_aluno_matricula_irregular(self):
        coordenadores = get_coordenadores_estagio(self.aprendiz)
        coordenadores_emails = get_coordenadores_emails(coordenadores)
        coordenadores_vinculos = get_coordenadores_vinculos(coordenadores)

        titulo = '[SUAP] Notificação de Aprendizagem com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_matricula_irregular.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'nomes_coordenadores': get_coordenadores_nomes(coordenadores),
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                'versao': 'coordenacao_de_extensao',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, coordenadores_vinculos)
        if coordenadores_emails:
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=coordenadores_emails,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def get_data_envio_notificacao(self):
        return self.prazo_final_regularizacao_matricula_irregular + relativedelta(days=-7)

    def notificar_aluno_interrupcao(self):
        titulo = '[SUAP] Notificação de Rescisão/Encerramento de Aprendizagem'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_interrupcao.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'data_envio_notificacao': self.get_data_envio_notificacao(),
                'versao': 'aprendiz',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aprendiz.get_vinculo()])
        email_aluno = self.get_email_aprendiz()
        if email_aluno:
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_INTERRUPCAO,
                notificador=None,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_orientador_interrupcao(self):
        titulo = '[SUAP] Notificação de Interrupção de Aprendizagem'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_interrupcao.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'nome_orientador': self.orientador.get_nome(),
                'versao': 'orientador',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_INTERRUPCAO,
                notificador=None,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def notificar_empregado_monitor_sobre_interrupcao_aprendizagem(self):
        coordenadores = get_coordenadores_estagio(self.aprendiz)
        titulo = 'Notificação de Aprendiz com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_interrupcao.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.aprendiz.matricula,
                'situacao_aprendiz': self.aprendiz.situacao.descricao,
                'nome_monitor': self.nome_monitor,
                'emails_coordenadores': get_coordenadores_emails(coordenadores),
                'versao': 'monitor',
            },
        )

        email_monitor = self.email_monitor
        if email_monitor:
            send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [email_monitor])
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_INTERRUPCAO,
                notificador=None,
                email_destinatario=email_monitor,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def verificar_envio_relatorio_frequencia(self):
        if self.periodicidade_envio_relatorio_frequencia:
            ultimo_periodo_frequencia = self.transformar_em_datas_passadas(self.ultimo_periodo_frequencia())
            inicio = ultimo_periodo_frequencia[0]
            fim = ultimo_periodo_frequencia[1]
            if not self.ha_relatorio_frequencia_ultimo_periodo_frequencia(inicio, fim):
                self.enviar_relatorio_frequencia(inicio, fim)

    def notificar_pendencias_assinatura_relatorios_modulos(self):
        for relatorio in RelatorioModuloAprendizagem.objects.filter(modulo_aprendizagem__aprendizagem=self, relatorio=''):
            relatorio.notificar_pendencia_de_assinatura_aprendiz()
            relatorio.notificar_pendencia_de_assinatura_orientador()
            relatorio.notificar_pendencia_de_assinatura_monitor()

    def notificar_orientador_divergencia_relatorios_modulo_aprendizagem(self):
        for relatorio_aluno in RelatorioModuloAprendizagem.objects.filter(
            modulo_aprendizagem__aprendizagem=self, eh_relatorio_do_empregado_monitor=False
        ):
            if relatorio_aluno.eh_relatorio_eletronico() and relatorio_aluno.possui_divergencias_com_contraparte():
                titulo = '[SUAP] Notificação: Divergência em Relatórios de Atividades da Aprendizagem'
                mensagem = render_to_string(
                    template_name='notificacoes/aprendizagem_divergencia_rel_atividades.html',
                    context={
                        'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                        'matricula_aprendiz': self.aprendiz.matricula,
                        'nome_orientador': self.orientador.get_nome(),
                        'url_aprendizagem': f'{settings.SITE_URL}{self.get_absolute_url()}',
                    },
                )

                vinculo_orientador = self.orientador.vinculo
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_orientador])

                notificacao = NotificacaoAprendizagem(
                    aprendizagem=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoAprendizagem.NOTIFICACAO_DIVERGENCIA_RELATORIO_ATIVIDADES,
                    notificador=None,
                    email_destinatario=vinculo_orientador.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()
                modulo_notificado = ModuloComPendenciaNotificado(modulo=relatorio_aluno.modulo_aprendizagem, notificacao=notificacao)
                modulo_notificado.save()
                break

    def notificar_orientador_necessidade_revisao(self):
        if RelatorioModuloAprendizagem.objects.filter(modulo_aprendizagem__aprendizagem=self, requer_revisao_orientador=True).exists():
            titulo = '[SUAP] Notificação: Pendência de revisão de Relatórios de Atividades da Aprendizagem'
            mensagem = render_to_string(
                template_name='notificacoes/aprendizagem_revisao_rel_atividades.html',
                context={
                    'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                    'matricula_aprendiz': self.aprendiz.matricula,
                    'nome_orientador': self.orientador.get_nome(),
                    'url_aprendizagem': f'{settings.SITE_URL}{self.get_absolute_url()}',
                },
            )

            vinculo_orientador = self.orientador.vinculo
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_orientador])

            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=get_datetime_now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_PENDENCIA_REVISAO_RELATORIO_ATIVIDADE,
                notificador=None,
                email_destinatario=vinculo_orientador.email_notificacao,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def transformar_em_datas_passadas(self, periodo):
        hoje = datetime.date.today()
        inicio = periodo[0]
        fim = periodo[1]
        dia_hoje = hoje.day
        if dia_hoje > fim:
            data_fim = datetime.date(hoje.year, hoje.month, fim)
        else:
            hoje_menos_um_mes = hoje + relativedelta(months=-1)
            ultimo_dia = calendar.monthrange(hoje_menos_um_mes.year, hoje_menos_um_mes.month)[1]
            if fim > ultimo_dia:
                data_fim = datetime.date(hoje_menos_um_mes.year, hoje_menos_um_mes.month, ultimo_dia)
            else:
                data_fim = datetime.date(hoje_menos_um_mes.year, hoje_menos_um_mes.month, fim)
        if dia_hoje > inicio and dia_hoje > fim:
            data_inicio = datetime.date(hoje.year, hoje.month, inicio)
        elif fim > inicio:
            data_inicio = datetime.date(hoje.year, hoje.month, inicio) + relativedelta(months=-1)
        else:
            mes_desejado = data_fim.month - 1
            ano_desejado = hoje.year
            if data_fim.month == 1:
                mes_desejado = 12
                ano_desejado = hoje.year - 1
            data_inicio = datetime.date(ano_desejado, mes_desejado, calendar.monthrange(ano_desejado, mes_desejado)[1])
        if data_inicio.day != inicio:
            data_inicio = data_inicio + relativedelta(days=1)
        return [data_inicio, data_fim]

    def ultimo_periodo_frequencia(self):
        dia_hoje = datetime.date.today().day
        if self.periodicidade_envio_relatorio_frequencia == self.MENSAL:
            # Campos definidos no modelo de Aprendizagem
            return [self.inicio_periodo_frequencia_1, self.fim_periodo_frequencia_1]
        else:
            if self.distancia_em_dias(self.fim_periodo_frequencia_1, dia_hoje) < self.distancia_em_dias(self.fim_periodo_frequencia_2, dia_hoje):
                return [self.inicio_periodo_frequencia_1, self.fim_periodo_frequencia_1]
            else:
                return [self.inicio_periodo_frequencia_2, self.fim_periodo_frequencia_2]

    def distancia_em_dias(self, dia_anterior, dia_atual):
        if dia_atual == dia_anterior:
            return 31
        elif dia_atual > dia_anterior:
            return dia_atual - dia_anterior
        else:
            return 31 - dia_anterior + dia_atual

    # def hoje_eh_dia_enviar_relatorio_frequendia(self):
    #    return datetime.date.today().day in self.dias_envio_relatorio_frequendia()

    def ha_relatorio_frequencia_ultimo_periodo_frequencia(self, inicio, fim):
        return RelatorioFrequenciaNotificacaoAprendizagem.objects.filter(notificacao_aprendizagem__aprendizagem=self, inicio=inicio, fim=fim).exists()

    # def dias_envio_relatorio_frequendia(self):
    #     dias = list()
    #     if self.periodicidade_envio_relatorio_frequencia == self.MENSAL:
    #         dias.append(self.fim_periodo_frequencia_1+1)
    #     elif self.periodicidade_envio_relatorio_frequencia == self.QUINZENAL:
    #         dias.append(self.fim_periodo_frequencia_1+1)
    #         dias.append(self.fim_periodo_frequencia_2+1)
    #     return dias

    def enviar_relatorio_frequencia(self, inicio, fim):
        aulas = Aula.objects.filter(
            professor_diario__diario__matriculadiario__matricula_periodo__aluno=self.aprendiz, data__gte=inicio, data__lte=fim, quantidade__gt=0
        )
        quantidade_aulas = aulas.aggregate(Sum('quantidade')).get('quantidade__sum') or 0
        if quantidade_aulas >= 1:
            faltas = Falta.objects.filter(matricula_diario__matricula_periodo__aluno=self.aprendiz, aula__in=aulas, abono_faltas=None)
            datas = aulas.values_list('data', flat=True).distinct()
            registros = []
            for data in datas:
                quantidade_aula_data = aulas.filter(data=data).aggregate(Sum('quantidade')).get('quantidade__sum') or 0
                percentagem_aula_data = 100 * quantidade_aula_data / float(quantidade_aulas)
                quantidade_faltas = faltas.filter(aula__data=data).aggregate(Sum('quantidade')).get('quantidade__sum') or 0
                percentagem_falta_data = 100 * quantidade_faltas / float(quantidade_aulas)
                registro = {
                    'data_periodo': format_(data),
                    'percentagem_presencas': percentagem_aula_data - percentagem_falta_data,
                    'percentagem_faltas': percentagem_falta_data,
                    'percentagem_aulas': percentagem_aula_data,
                }
                registros.append(registro)

            total_faltas = faltas.aggregate(Sum('quantidade')).get('quantidade__sum') or 0
            percentagem_total_faltas = 100 * total_faltas / float(quantidade_aulas)
            total_presencas_abonos = quantidade_aulas - total_faltas
            percentagem_presencas_abonos = 100 * total_presencas_abonos / float(quantidade_aulas)
            registros.append(
                {
                    'data_periodo': f'de {format_(inicio)} até {format_(fim)}',
                    'percentagem_presencas': percentagem_presencas_abonos,
                    'percentagem_faltas': percentagem_total_faltas,
                    'percentagem_aulas': 100,
                }
            )
            titulo = f'Notificação de Relatório de Presença do Jovem Aprendiz {self.aprendiz}'
            mensagem = render_to_string(
                template_name='notificacoes/aprendizagem_relatorio_frequencia.html',
                context={
                    'aprendiz': str(self.aprendiz),
                    'empresa': str(self.empresa),
                    'inicio': inicio,
                    'fim': fim,
                    'registros': registros,
                    'horario_geracao': datetime.datetime.now(),
                    'versao': 'com_aulas',
                },
            )
        elif quantidade_aulas == 0:
            titulo = f'Notificação de Relatório de Presença do Jovem Aprendiz {self.aprendiz}'
            mensagem = render_to_string(
                template_name='notificacoes/aprendizagem_relatorio_frequencia.html',
                context={
                    'aprendiz': str(self.aprendiz),
                    'empresa': str(self.empresa),
                    'inicio': inicio,
                    'fim': fim,
                    'horario_geracao': datetime.datetime.now(),
                    'versao': 'sem_aulas',
                },
            )
        emails_relatorio_frequencia = self.emails_relatorio_frequencia.split(',')
        if emails_relatorio_frequencia:
            send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, emails_relatorio_frequencia)
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_RELATORIO_FRENQUENCIA,
                notificador=None,
                email_destinatario=self.emails_relatorio_frequencia,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()
            informacoes_relatorio = RelatorioFrequenciaNotificacaoAprendizagem(inicio=inicio, fim=fim, notificacao_aprendizagem=notificacao)
            informacoes_relatorio.save()

    def notificar_orientador_pendencia_visita(self):
        if not self.data_encerramento:
            for modulo in self.moduloaprendizagem_set.all():
                if (datetime.date.today() + relativedelta(days=20)) == modulo.fim and not self.visitaaprendizagem_set.exists():
                    titulo = '[SUAP] Pendência de Visita de Orientação de Aprendizagem'
                    mensagem = render_to_string(
                        template_name='notificacoes/aprendizagem_visita_pendente.html',
                        context={
                            'nome_aprendiz': normalizar_nome_proprio(self.aprendiz.get_nome_social_composto()),
                            'matricula_aprendiz': self.aprendiz.matricula,
                            'modulo': modulo,
                            'inicio_modulo': modulo.inicio,
                            'fim_modulo': modulo.fim,
                            'url_aprendizagem': f'{settings.SITE_URL}{self.get_absolute_url()}',
                            'versao': 'prazo_proximo_expiracao',
                        },
                    )

                    send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
                    if self.orientador.vinculo.user.email:
                        notificacao = NotificacaoAprendizagem(
                            aprendizagem=self,
                            data=datetime.datetime.now(),
                            tipo=NotificacaoAprendizagem.NOTIFICACAO_VISITA,
                            notificador=None,
                            email_destinatario=self.orientador.vinculo.user.email,
                            mensagem_enviada=f'{titulo}<br/>{mensagem}',
                        )
                    notificacao.save()

    def pode_emitir_declaracao_de_participacao(self):
        user = tl.get_user()
        return self.data_encerramento is not None and (self.eh_aprendiz(user) or tem_permissao_de_coordenador(user, campus=self.aprendiz.campus))


class EnvioRelatorioFrequencia(models.ModelPlus):
    aprendizagem = models.ForeignKeyPlus(Aprendizagem)
    envio = models.DateFieldPlus('Data de Envio do Relatório')
    inicio_periodo = models.DateFieldPlus('Início do Período')
    fim_periodo = models.DateFieldPlus('Fim do Período')
    mensagem = models.TextField('Mensagem Enviada')
    emails = models.TextField('E-mails Recebedores')
    token = models.CharFieldPlus('Token')
    arquivo = models.FileFieldPlus(upload_to='estagios/relatorio_frequencia')


class ModuloAprendizagem(models.ModelPlus):
    MODULO_I = 1
    MODULO_II = 2
    MODULO_III = 3
    MODULO_IV = 4
    MODULO_CHOICES = [[MODULO_I, 'Módulo I'], [MODULO_II, 'Módulo II'], [MODULO_III, 'Módulo III'], [MODULO_IV, 'Módulo IV']]

    tipo_modulo = models.IntegerField('Tipo do Módulo', null=True, choices=MODULO_CHOICES)
    aprendizagem = models.ForeignKeyPlus(Aprendizagem, verbose_name='Aprendizagem')
    atividades = models.TextField('Descrição das Atividades do Módulo', help_text='Estas atividades serão utilizadas para as avaliações do módulo.')
    inicio = models.DateFieldPlus('Data de início do módulo')
    fim = models.DateFieldPlus('Data de fim do módulo')
    ch_teorica_semanal = models.IntegerField('Carga-Horária Teórica Semanal')
    ch_pratica_semanal = models.IntegerField('Carga-Horária Prática Semanal')

    def __str__(self):
        return f'{self.get_tipo_modulo_display()} (de {format_(self.inicio)} até {format_(self.fim)})'

    def get_tipo_modulo_display(self):
        texto_display = self.MODULO_CHOICES[self.tipo_modulo - 1][1]
        return texto_display.replace('Módulo', self.aprendizagem.nomenclatura_periodo)

    @property
    def inicio_submissao_relatorios(self):
        """
        Data para início da submissão de relatórios do módulo.
        Se módulo tiver mais de 3 meses, a submissão pode iniciar após a conclusão do primeiro trimestre.
        Se for inferior a isso, a submissão inicia *após* o fim do módulo.
        """
        return min(self.inicio + relativedelta(months=3, days=1), self.fim + relativedelta(days=1))

    def tem_relatorio_aprendiz(self):
        return self.relatorio_aprendiz is not None

    def tem_relatorio_monitor(self):
        return self.relatorio_monitor is not None

    def tem_visitas(self):
        return self.aprendizagem.visitaaprendizagem_set.filter(data_visita__range=(self.inicio, self.fim)).exists()

    @cached_property
    def relatorio_aprendiz(self):
        return self.relatoriomoduloaprendizagem_set.filter(eh_relatorio_do_empregado_monitor=False).first()

    @cached_property
    def relatorio_monitor(self):
        return self.relatoriomoduloaprendizagem_set.filter(eh_relatorio_do_empregado_monitor=True).first()

    @property
    def visitas(self):
        if self.visitaaprendizagem_set.exists():
            return self.aprendizagem.visitaaprendizagem_set.filter(data_visita__range=(self.inicio, self.fim))

    @cached_property
    def justificativa_visita(self):
        return self.justificativavisitamoduloaprendizagem_set.first()

    def ja_eh_tempo_de_cadastrar_relatorio(self, user):
        if tem_permissao_de_coordenador(user, campus=self.aprendizagem.aprendiz.campus):
            return not self.aprendizagem.data_encerramento
        elif self.aprendizagem.eh_aprendiz(user) or self.aprendizagem.eh_orientador(user) or self.aprendizagem.eh_monitor(user):
            return not self.aprendizagem.data_encerramento and self.inicio_submissao_relatorios <= get_datetime_now().date()
        return False

    @property
    def foi_iniciado(self):
        return self.inicio <= datetime.date.today()

    @property
    def esta_encerrado(self):
        return self.fim < datetime.date.today()


class AditivoContratualAprendizagem(models.ModelPlus):
    aprendizagem = models.ForeignKeyPlus(Aprendizagem, verbose_name='Aprendizagem')
    tipos_aditivo = models.ManyToManyField('estagios.TipoAditivoAprendizagem', verbose_name='Tipos de Aditivo Contratual', blank=False)
    inicio_vigencia = models.DateFieldPlus('Início da Vigência', blank=False)
    aditivo = models.FileFieldPlus('Aditivo', blank=False, max_length=255, upload_to='aprendizagem/aditivo_aprendizagem')
    descricao = models.TextField('Descrição', null=True, blank=True)

    historico = models.TextField('Histórico', null=True)

    class Meta:
        verbose_name = 'Aditivo Contratual de Aprendizagem'
        verbose_name_plural = 'Aditivos Contratuais de Aprendizagem'

    def __str__(self):
        lista = []
        for tipo_aditivo in self.tipos_aditivo.all():
            lista.append(str(tipo_aditivo))
        return 'Descrição: {} <br>Tipos: {}'.format(self.descricao, ', '.join(lista))

    def save(self):
        super().save()
        self.aprendizagem.save()


class TipoAditivoAprendizagem(models.ModelPlus):
    # tipos de aditivo
    # são as próprias instâncias possíveis deste modelo
    # há apenas 1 instância por tipo de aditivo
    # o id de cada instância é o próprio valor da constante
    # veja o método 'popula_tipos_aditivos'
    PROFESSOR_ORIENTADOR = 1
    TEMPO = 2
    EMPREGADO_MONITOR = 3
    HORARIO = 4
    FILIAL = 5  # demanda 562

    TIPO_CHOICES = [
        [PROFESSOR_ORIENTADOR, 'Professor Orientador'],
        [TEMPO, 'Tempo'],
        [EMPREGADO_MONITOR, 'Empregado Monitor'],
        [HORARIO, 'Horário'],
        [FILIAL, 'Mudança de Filial/Empresa'],
    ]

    descricao = models.CharFieldPlus('Decrição')

    class Meta:
        verbose_name = 'Tipo de Aditivo Contratual Aprendizagem'
        verbose_name_plural = 'Tipos de Aditivo Contratual Aprendizagem'

    @staticmethod
    def popula_tipos_aditivos():
        for tipo_aditivo in TipoAditivoAprendizagem.TIPO_CHOICES:
            tipo_aditivo_id = tipo_aditivo[0]
            tipo_aditivo_descricao = tipo_aditivo[1]
            # cria APENAS se não existir, pois este modelo é usado como FK
            TipoAditivoAprendizagem.objects.get_or_create(id=tipo_aditivo_id, descricao=tipo_aditivo_descricao)

    def __str__(self):
        return f'{self.descricao}'


class VisitaAprendizagem(models.ModelPlus):
    aprendizagem = models.ForeignKeyPlus(Aprendizagem, verbose_name='Aprendizagem')
    modulo_aprendizagem = models.ForeignKeyPlus(ModuloAprendizagem, verbose_name='Módulo', default=None, null=True)
    orientador = models.ForeignKeyPlus(Professor, verbose_name='Orientador')

    # Dados gerais
    data_visita = models.DateFieldPlus('Data da Visita')

    # Parecer da visita
    ambiente_adequado = models.BooleanField(
        'Ambiente Adequado', default=False, help_text='O ambiente de trabalho está adequado ao desenvolvimento das atividades do aprendiz?'
    )
    ambiente_adequado_justifique = models.TextField(
        'Justificativa para Ambiente Inadequado',
        default='',
        blank=True,
        help_text='Preencher somente em caso de resposta negativa ao quesito anterior.',
    )
    desenvolvendo_atividades_previstas = models.BooleanField(
        'Desenvolvimento Atividades Previstas',
        default=False,
        help_text='O aprendiz está desenvolvendo as atividades previstas no contrato de trabalho para este módulo?',
    )
    desenvolvendo_atividades_nao_previstas = models.BooleanField(
        'Desenvolvimento Atividades Não-Previstas',
        default=False,
        help_text='Existem atividades que estão sendo desenvolvidas (da competência do aprendiz), mas que não estão previstas no contrato de trabalho para este módulo?',
    )
    atividades_nao_previstas = models.TextField(
        'Atividades Não-Previstas',
        help_text='Se sim, descreva abaixo as atividades desenvolvidas que não foram previstas no plano de atividades, informando ao coordenador de estágios do campus do aluno a necessidade da sua atualização.',
        blank=True,
    )

    desenvolvendo_atividades_fora_competencia = models.BooleanField(
        'Desenvolvimento Atividades Fora da Competência',
        default=False,
        help_text='Existem atividades que estão sendo desenvolvidas fora das competências do aprendiz?',
    )

    apoiado_pelo_supervidor = models.BooleanField(
        'Apoiado pelo Supervisor',
        default=False,
        help_text='O aprendiz está sendo apoiado/orientado/supervisionado pelo empregado monitor desta aprendizagem na concedente?',
    )
    direitos_respeitados = models.BooleanField(
        'Direitos Respeitados',
        default=False,
        help_text='Os pagamentos mensais e demais benefícios, bem como o horário de trabalho estão sendo respeitados?',
    )
    direitos_respeitados_especificar = models.TextField(
        'Especificar direitos não respeitados',
        default='',
        blank=True,
        help_text='Preencher somente em caso de resposta negativa ao quesito anterior.',
    )
    aprendizagem_satisfatoria = models.BooleanField(
        'Aprendizagem Satisfatória',
        default=False,
        help_text='De um modo geral, quanto à contribuição ao aprendizado do aluno, as atividades estão ocorrendo de forma satisfatória?',
    )
    informacoes_adicionais = models.TextField(
        'Informações Adicionais',
        help_text='Espaço reservado ao registro de informações que considerar relevantes. (ex.: no caso alguma questão não tenha sido respondida, justificar; ou fazer o relato de outras informações colhidas durante a visita.)',
        blank=True,
    )
    relatorio = models.FileFieldPlus(
        'Relatório de Visita',
        help_text='Inserir o relatório de visita devidamente assinado. Limite de tamanho do arquivo 2MB.',
        blank=True,
        null=True,
        upload_to='visita_aprendizagem/relatorio',
        max_file_size=2097152,
    )
    ultimo_editor = models.ForeignKeyPlus('comum.User', verbose_name='Último Usuário a Editar', null=True)
    relatorio_interno = models.FileFieldPlus(
        'Relatório de Visita Gerado',
        help_text='Relatório gerado pelo sistema após o preenchimento deste formulário.',
        blank=True,
        null=True,
        upload_to='visita_pratica_profissional/relatorio_interno',
        max_file_size=2097152,
    )
    assinatura_orientador = models.ForeignKeyPlus(
        'AssinaturaEletronica', verbose_name='Assinatura Eletrônica do Orientador', null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = 'Visita do Orientador'
        verbose_name_plural = 'Visitas do Orientador'

    def __str__(self):
        return f'Visita realizada em {format_(self.data_visita)}'

    def save(self):
        self.modulo_aprendizagem = self.aprendizagem.moduloaprendizagem_set.filter(inicio__lte=self.data_visita, fim__gte=self.data_visita)[0]
        super().save()

    def can_delete(self, user=None):
        return self.orientador.vinculo == user.get_vinculo()


class OrientacaoAprendizagem(models.ModelPlus):
    aprendizagem = models.ForeignKeyPlus(Aprendizagem, verbose_name='Aprendizagem')
    orientador = models.ForeignKeyPlus(Professor, verbose_name='Orientador')
    data = models.DateFieldPlus(verbose_name='Data da Reunião de Orientação')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    local = models.CharFieldPlus('Local')
    descricao = models.TextField('Descrição do Conteúdo da Orientação', blank=True, null=True)

    class Meta:
        ordering = ('-data',)

    def save(self, *args, **kwargs):
        titulo = '[SUAP] Orientação de Aprendizagem Agendada'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_orientacao_agendada.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.aprendizagem.aprendiz.get_nome_social_composto()),
                'nome_orientador': self.aprendizagem.orientador.get_nome(),
                'matricula_orientador': self.aprendizagem.orientador.get_matricula(),
                'empresa': self.aprendizagem.empresa,
                'data_reuniao': self.data,
                'horario_reuniao': self.hora_inicio,
                'local_reuniao': self.local,
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aprendizagem.aprendiz.get_vinculo()])
        email_aprendiz = self.aprendizagem.get_email_aprendiz()
        if email_aprendiz:
            notificacao = NotificacaoAprendizagem(
                aprendizagem=self.aprendizagem,
                data=datetime.datetime.now(),
                tipo=NotificacaoAprendizagem.NOTIFICACAO_ORIENTACAO_APRENDIZAGEM,
                notificador=self.user,
                email_destinatario=email_aprendiz,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()
        super().save()


class RelatorioModuloAprendizagem(models.ModelPlus):
    AVALICAO_CONCEITO_EXCELENTE = 1
    AVALICAO_CONCEITO_BOM = 2
    AVALICAO_CONCEITO_REGULAR = 3
    AVALICAO_CONCEITO_RUIM = 4
    AVALICAO_CONCEITO_PESSIMO = 5
    AVALICAO_CONCEITO_CHOICES = [
        [AVALICAO_CONCEITO_EXCELENTE, 'Excelente'],
        [AVALICAO_CONCEITO_BOM, 'Bom'],
        [AVALICAO_CONCEITO_REGULAR, 'Regular'],
        [AVALICAO_CONCEITO_RUIM, 'Ruim'],
        [AVALICAO_CONCEITO_PESSIMO, 'Péssimo'],
    ]

    REALIZADA_SIM = 1
    REALIZADA_NAO = 2
    PARCIALMENTE_REALIZADA = 3
    REALIZADA_CHOICES = [[REALIZADA_SIM, 'Realizadas'], [REALIZADA_NAO, 'Não Realizadas'], [PARCIALMENTE_REALIZADA, 'Parcialmente Realizadas']]

    modulo_aprendizagem = models.ForeignKeyPlus(ModuloAprendizagem, verbose_name='Módulo da Aprendizagem')
    eh_relatorio_do_empregado_monitor = models.BooleanField(editable=False, default=True)

    # Dados gerais
    data_relatorio = models.DateFieldPlus('Data do Relatório', blank=False, null=True)

    # Atividades Previstas
    avaliacao_atividades = models.IntegerField('Sobre as Atividades', choices=REALIZADA_CHOICES)

    # Desenvolvimento das atividades
    comentarios_atividades = models.TextField(
        'Detalhe a realização das atividades',
        null=True,
        blank=True,
        help_text='Descreva atividades que foram realizadas total ou parcialmente, ou que não foram realizadas e justifique.',
    )

    # Atividades não-previstas
    outras_atividades = models.TextField('Realizou atividades não previstas no resumo do curso? Informe e justifique', blank=True, null=True)

    # relação teoria/prática (somente relatório do aprendiz)
    aprendizagem_na_area_formacao = models.IntegerField(
        'Área de Formação',
        blank=False,
        null=True,
        help_text='A aprendizagem foi/está sendo desenvolvida em sua área de formação?',
        choices=[[1, 'Sim'], [0, 'Não']],
    )
    aprendizagem_contribuiu = models.IntegerField(
        'Contribuição da Aprendizagem',
        blank=False,
        null=True,
        help_text='As atividades desenvolvidas contribuíram para a sua formação?',
        choices=[[1, 'Sim'], [0, 'Não']],
    )
    aplicou_conhecimento = models.IntegerField(
        'Aplicação do Conhecimento',
        blank=False,
        null=True,
        help_text='Você teve oportunidade de aplicar os conhecimentos adquiridos no seu Curso?',
        choices=[[1, 'Sim'], [0, 'Não']],
    )

    # avaliação do aprendiz (somente relatório do aprendiz)
    avaliacao_conceito = models.IntegerField(
        'Conceito',
        help_text='Qual conceito você atribui ao desenvolvimento de suas atividades neste módulo?',
        choices=AVALICAO_CONCEITO_CHOICES,
        null=True,
        blank=False,
    )

    # comentários do aprendiz sobre desenvolvimento das atividades (somente relatório do aprendiz)
    avaliacao_geral_atividades_aprendiz = models.TextField(
        'Comentários gerais sobre o desenvolvimento das atividades',
        null=True,
        blank=True,
        help_text='Deixe um comentário sobre como você avalia, de um modo geral, o desenvolvimento das atividades.',
    )

    avaliacao_comentarios = models.TextField(
        'Comentários e Sugestões',
        null=True,
        blank=True,
        help_text='Insira comentários e/ou sugestões sobre o programa de aprendizagem da empresa, sobre algum ponto '
        'específico na realização das atividades, ou sobre este módulo.',
    )

    # avaliação de desempenho do aprendiz(somente empregado monitor)
    nota_aprendiz = models.IntegerField(
        'Nota do Aprendiz',
        choices=[[nota, nota] for nota in range(10 + 1)],
        null=True,
        blank=False,
        help_text='Dê uma nota ao aprendiz que avalie seu desempenho como um todo de 0 a 10.',
    )

    # upload do arquivo do relatório
    relatorio = models.FileFieldPlus(
        'Relatório do Módulo',
        blank=True,
        null=True,
        upload_to='relatorio_modulo_aprendizagem/relatorio',
        max_file_size=2097152,
        help_text='O relatório do módulo deve estar assinado pelo Aprendiz e pelo Empregado Monitor. Limite de tamanho do arquivo de 2MB. '
        'Ao anexar o arquivo, o relatório não poderá ser assinado eletronicamente.',
        can_view='can_view_relatorio',
    )

    ultimo_editor = models.ForeignKeyPlus('comum.User', verbose_name='Último Usuário a Editar', null=True)

    relatorio_interno = models.FileFieldPlus(
        'Relatório do Módulo',
        help_text='Relatório gerado pelo sistema após o preenchimento deste formulário.',
        blank=True,
        null=True,
        upload_to='relatorio_modulo_aprendizagem/relatorio_interno',
        max_file_size=2097152,
    )

    # assinaturas
    assinatura_aprendiz = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Aprendiz',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='relatorios_aprendizagem_aprendiz',
    )
    assinatura_orientador = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Orientador',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='relatorios_aprendizagem_orientador',
    )
    assinatura_monitor = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Monitor',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='relatorios_aprendizagem_monitor',
    )

    requer_revisao_orientador = models.BooleanFieldPlus(verbose_name='Requer revisão do orientador', default=False)

    class Meta:
        verbose_name = 'Relatório de Atividades do Módulo da Aprendizagem'
        verbose_name_plural = 'Relatórios de Atividades dos Módulos da Aprendizagem'

    def __str__(self):
        return f'Relatório do {self.modulo_aprendizagem.aprendizagem.nomenclatura_periodo} ({self.pk})'

    def save(self):
        super().save()
        self.modulo_aprendizagem.aprendizagem.save()

    def can_view_relatorio(self, user):
        if user.has_perm('estagios.view_aprendizagem'):
            return True
        aprendizagem = self.modulo_aprendizagem.aprendizagem
        return aprendizagem.eh_aprendiz(user) or aprendizagem.eh_orientador(user) or aprendizagem.eh_monitor(user)

    def pode_editar(self, user=None):
        if self.modulo_aprendizagem.aprendizagem.data_encerramento:
            return False
        if self.eh_relatorio_do_empregado_monitor:
            return self.modulo_aprendizagem.aprendizagem.pode_cadastrar_relatorio_monitor(user)
        return self.modulo_aprendizagem.aprendizagem.pode_cadastrar_relatorio_aprendiz(user)

    def can_delete(self, user=None):
        return not self.modulo_aprendizagem.aprendizagem.data_encerramento

    def eh_relatorio_eletronico(self):
        return not self.relatorio

    def atividades_foram_realizadas(self):
        return self.avaliacao_atividades == RelatorioModuloAprendizagem.REALIZADA_SIM

    def atividades_foram_realizadas_parcialmente(self):
        return self.avaliacao_atividades == RelatorioModuloAprendizagem.PARCIALMENTE_REALIZADA

    def get_situacao_assinaturas(self):
        return (
            ('Aprendiz', self.assinatura_aprendiz is not None),
            ('Empregado(a) Monitor(a)', self.assinatura_monitor is not None),
            ('Orientador(a)', self.assinatura_orientador is not None),
        )

    @property
    def assinaturas_pendentes(self):
        """
        Retorna apenas os nomes dos signatários que ainda não assinaram o relatório.
        """
        return [tupla[0] for tupla in filter(lambda situacao: not situacao[1], self.get_situacao_assinaturas())]

    def pode_assinar(self, user=None):
        user = user or tl.get_user()
        aprendizagem = self.modulo_aprendizagem.aprendizagem
        if aprendizagem.eh_aprendiz(user) and not self.assinatura_aprendiz:
            return True
        if aprendizagem.eh_orientador(user) and not self.assinatura_orientador:
            return True
        return bool(aprendizagem.eh_monitor(user) and not self.assinatura_monitor)

    def assinar(self, user):
        vinculo = user.get_vinculo()
        assinatura = AssinaturaEletronica(vinculo=vinculo)
        assinatura.assinar()
        aprendizagem = self.modulo_aprendizagem.aprendizagem
        if aprendizagem.eh_aprendiz(user):
            self.assinatura_aprendiz = assinatura
        if aprendizagem.eh_orientador(user):
            self.assinatura_orientador = assinatura
        if aprendizagem.eh_monitor(user):
            self.assinatura_monitor = assinatura
        self.save()

    def invalidar_assinaturas(self):
        for assinatura in (self.assinatura_aprendiz, self.assinatura_orientador, self.assinatura_monitor):
            if assinatura is not None:
                assinatura.delete()
        self.refresh_from_db(fields=['assinatura_aprendiz', 'assinatura_orientador', 'assinatura_monitor'])

    def resetar_relatorio_eletronico(self):
        self.invalidar_assinaturas()
        self.relatorio_interno.delete()

    @property
    def relatorio_contraparte(self):
        return RelatorioModuloAprendizagem.objects.filter(
            modulo_aprendizagem=self.modulo_aprendizagem, eh_relatorio_do_empregado_monitor=not self.eh_relatorio_do_empregado_monitor
        ).first()

    def possui_divergencias_com_contraparte(self):
        """
        Verifica se relatório do aluno possui divergências com o do monitor, e vice-versa.
        """
        from .utils import get_divergencias_relatorios_modulo_aprendizagem

        rel_aluno = self if not self.eh_relatorio_do_empregado_monitor else self.relatorio_contraparte
        rel_monitor = self if self.eh_relatorio_do_empregado_monitor else self.relatorio_contraparte

        return bool(get_divergencias_relatorios_modulo_aprendizagem(rel_aluno, rel_monitor))

    def pode_resolver_divergencias(self, user):
        return self.modulo_aprendizagem.aprendizagem.eh_orientador(user)

    def pode_coletar_assinaturas_eletronicas(self):
        return (
            self.eh_relatorio_eletronico()
            and self.relatorio_contraparte
            and not self.requer_revisao_orientador
            and not self.possui_divergencias_com_contraparte()
        )

    # Notificações
    def notificar_pendencia_de_assinatura_aprendiz(self):
        if self.pode_coletar_assinaturas_eletronicas() and not self.assinatura_aprendiz:
            vinculo_aluno = self.modulo_aprendizagem.aprendizagem.aprendiz.get_vinculo()
            tipo_notificacao = NotificacaoAprendizagem.NOTIFICACAO_ASSINATURA_RELATORIO_MONITOR
            # evita envios repetitivos num curto período
            if not NotificacaoAprendizagem.objects.filter(
                aprendizagem=self.modulo_aprendizagem.aprendizagem,
                tipo=tipo_notificacao,
                email_destinatario=vinculo_aluno.email_notificacao,
                data__gte=datetime.datetime.now() - timedelta(hours=1),
            ).exists():
                url_relatorios = (
                    f'{settings.SITE_URL}{self.modulo_aprendizagem.aprendizagem.get_absolute_url()}'
                    f'?tab={"avaliacaomonitor" if self.eh_relatorio_do_empregado_monitor else "relatorios"}'
                )
                if self.eh_relatorio_do_empregado_monitor:
                    descricao_relatorio = 'Relatório de Atividades de Aprendizagem do seu monitor'
                else:
                    descricao_relatorio = 'seu Relatório de Atividades de Aprendizagem'

                titulo = '[SUAP] Notificação: Pendência de Assinatura em Relatório de Atividades da Aprendizagem'
                mensagem = render_to_string(
                    template_name='notificacoes/aprendizagem_pendencia_assinatura_relatorio.html',
                    context={
                        'nome_aprendiz': normalizar_nome_proprio(self.modulo_aprendizagem.aprendizagem.aprendiz.get_nome_social_composto()),
                        'descricao_relatorio': descricao_relatorio,
                        'url_relatorios': url_relatorios,
                        'versao': 'aprendiz',
                    },
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_aluno])
                notificacao = NotificacaoAprendizagem(
                    aprendizagem=self.modulo_aprendizagem.aprendizagem,
                    data=datetime.datetime.now(),
                    tipo=tipo_notificacao,
                    notificador=None,
                    email_destinatario=vinculo_aluno.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()
                modulo_notificado = ModuloComPendenciaNotificado(modulo=self.modulo_aprendizagem, notificacao=notificacao)
                modulo_notificado.save()

    def notificar_pendencia_de_assinatura_orientador(self):
        if self.pode_coletar_assinaturas_eletronicas() and not self.assinatura_orientador:
            vinculo_orientador = self.modulo_aprendizagem.aprendizagem.orientador.get_vinculo()
            tipo_notificacao = NotificacaoAprendizagem.NOTIFICACAO_ASSINATURA_RELATORIO_MONITOR
            # evita envios repetitivos num curto período
            if not NotificacaoAprendizagem.objects.filter(
                aprendizagem=self.modulo_aprendizagem.aprendizagem,
                tipo=tipo_notificacao,
                email_destinatario=vinculo_orientador.email_notificacao,
                data__gte=datetime.datetime.now() - timedelta(hours=1),
            ).exists():
                url_relatorios = (
                    f'{settings.SITE_URL}{self.modulo_aprendizagem.aprendizagem.get_absolute_url()}'
                    f'?tab={"avaliacaomonitor" if self.eh_relatorio_do_empregado_monitor else "relatorios"}'
                )

                titulo = '[SUAP] Notificação: Pendência de Assinatura em Relatório de Atividades da Aprendizagem'
                mensagem = render_to_string(
                    template_name='notificacoes/aprendizagem_pendencia_assinatura_relatorio.html',
                    context={
                        'nome_aprendiz': normalizar_nome_proprio(self.modulo_aprendizagem.aprendizagem.aprendiz.get_nome_social_composto()),
                        'matricula_aprendiz': self.modulo_aprendizagem.aprendizagem.aprendiz.matricula,
                        'nome_orientador': self.modulo_aprendizagem.aprendizagem.orientador.get_nome(),
                        'url_relatorios': url_relatorios,
                        'versao': 'orientador',
                    },
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_orientador])
                notificacao = NotificacaoAprendizagem(
                    aprendizagem=self.modulo_aprendizagem.aprendizagem,
                    data=datetime.datetime.now(),
                    tipo=tipo_notificacao,
                    notificador=None,
                    email_destinatario=vinculo_orientador.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()
                modulo_notificado = ModuloComPendenciaNotificado(modulo=self.modulo_aprendizagem, notificacao=notificacao)
                modulo_notificado.save()

    def notificar_pendencia_de_assinatura_monitor(self):
        if self.pode_coletar_assinaturas_eletronicas() and not self.assinatura_monitor and self.modulo_aprendizagem.aprendizagem.monitor:
            vinculo_monitor = self.modulo_aprendizagem.aprendizagem.monitor
            tipo_notificacao = NotificacaoAprendizagem.NOTIFICACAO_ASSINATURA_RELATORIO_MONITOR
            # evita envios repetitivos num curto período
            if not NotificacaoAprendizagem.objects.filter(
                aprendizagem=self.modulo_aprendizagem.aprendizagem,
                tipo=tipo_notificacao,
                email_destinatario=vinculo_monitor.email_notificacao,
                data__gte=datetime.datetime.now() - timedelta(hours=1),
            ).exists():
                url_relatorios = (
                    f'{settings.SITE_URL}{self.modulo_aprendizagem.aprendizagem.get_absolute_url()}'
                    f'?tab={"avaliacaomonitor" if self.eh_relatorio_do_empregado_monitor else "relatorios"}'
                )
                if self.eh_relatorio_do_empregado_monitor:
                    descricao_relatorio = 'seu Relatório de Atividades da Aprendizagem'
                else:
                    descricao_relatorio = 'Relatório de Atividades de uma Aprendizagem sob sua monitoria'

                titulo = '[SUAP] Notificação: Pendência de Assinatura em Relatório de Atividades da Aprendizagem'
                mensagem = render_to_string(
                    template_name='notificacoes/aprendizagem_pendencia_assinatura_relatorio.html',
                    context={
                        'nome_monitor': self.modulo_aprendizagem.aprendizagem.nome_monitor,
                        'descricao_relatorio': descricao_relatorio,
                        'url_relatorios': url_relatorios,
                        'versao': 'monitor',
                    },
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_monitor])
                notificacao = NotificacaoAprendizagem(
                    aprendizagem=self.modulo_aprendizagem.aprendizagem,
                    data=datetime.datetime.now(),
                    tipo=tipo_notificacao,
                    notificador=None,
                    email_destinatario=vinculo_monitor.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()
                modulo_notificado = ModuloComPendenciaNotificado(modulo=self.modulo_aprendizagem, notificacao=notificacao)
                modulo_notificado.save()


class RelatorioFrequenciaNotificacaoAprendizagem(models.ModelPlus):
    inicio = models.DateFieldPlus('Início do Período de Apuração')
    fim = models.DateFieldPlus('Fim do Período de Apuração')
    notificacao_aprendizagem = models.ForeignKeyPlus('estagios.NotificacaoAprendizagem', verbose_name='Notificação')

    class Meta:
        verbose_name = 'Informações do Relatório de Frequência'
        verbose_name_plural = 'Informações do Relatório de Frequência'

    def __str__(self):
        return f'Informações do Relatório de Frequência ({self.pk})'


class NotificacaoAprendizagem(models.ModelPlus):
    NOTIFICACAO_INICIAL_PROFESSORES_DIARIOS = 1
    NOTIFICACAO_INICIAL = 2
    NOTIFICACAO_ORIENTACAO_APRENDIZAGEM = 3
    NOTIFICACAO_VISITA = 4
    NOTIFICACAO_RELATORIO_APRENDIZ = 5
    NOTIFICACAO_RELATORIO_MONITOR = 6
    NOTIFICACAO_MATRICULA_IRREGULAR = 7
    NOTIFICACAO_INTERRUPCAO = 8
    NOTIFICACAO_RELATORIO_FRENQUENCIA = 9
    NOTIFICACAO_ASSINATURA_RELATORIO_APRENDIZ = 10
    NOTIFICACAO_ASSINATURA_RELATORIO_MONITOR = 11
    NOTIFICACAO_DIVERGENCIA_RELATORIO_ATIVIDADES = 12
    NOTIFICACAO_ASSINATURA_DECURSO_PRAZO_PENDENTE = 13
    NOTIFICACAO_PENDENCIA_REVISAO_RELATORIO_ATIVIDADE = 14

    TIPO_CHOICES = [
        [NOTIFICACAO_INICIAL_PROFESSORES_DIARIOS, 'Notificação inicial aos professores dos diários.'],
        [NOTIFICACAO_INICIAL, 'Notificação inicial.'],
        [NOTIFICACAO_ORIENTACAO_APRENDIZAGEM, 'Notificação de Orientação de Aprendizagem'],
        [NOTIFICACAO_VISITA, 'Notificação de Pendência de Visita'],
        [NOTIFICACAO_RELATORIO_APRENDIZ, 'Notificação de Pendência de Relatório de Avaliação pelo Aprendiz.'],
        [NOTIFICACAO_RELATORIO_MONITOR, 'Notificação de Pendência de Relatório de Avaliação pelo Empregado Monitor.'],
        [NOTIFICACAO_MATRICULA_IRREGULAR, 'Notificação de Matrícula Irregular do Aluno.'],
        [NOTIFICACAO_INTERRUPCAO, 'Notificação de Interrupção do Cadastro de Aprendizagem.'],
        [NOTIFICACAO_RELATORIO_FRENQUENCIA, 'Notificação de Relatório de Frequência.'],
        [NOTIFICACAO_ASSINATURA_RELATORIO_APRENDIZ, 'Notificação de Pendência de Assinatura em Relatório do Aprendiz.'],
        [NOTIFICACAO_ASSINATURA_RELATORIO_MONITOR, 'Notificação de Pendência de Assinatura em Relatório do Monitor.'],
        [NOTIFICACAO_DIVERGENCIA_RELATORIO_ATIVIDADES, 'Notificação de Divergência em Relatórios de Atividades da Aprendizagem.'],
        [NOTIFICACAO_ASSINATURA_DECURSO_PRAZO_PENDENTE, 'Notificação de necessidade de assinatura da justificativa de Decurso de Prazo.'],
        [NOTIFICACAO_PENDENCIA_REVISAO_RELATORIO_ATIVIDADE, 'Notificação de pendência de revisão de Relatório de Atividades da Aprendizagem.'],
    ]

    aprendizagem = models.ForeignKeyPlus(Aprendizagem, verbose_name='Aprendizagem')
    notificador = models.ForeignKeyPlus('comum.User', verbose_name='Notificador', null=True)
    data = models.DateTimeFieldPlus('Data da Notificação')
    tipo = models.IntegerField('Tipo', choices=TIPO_CHOICES)
    email_destinatario = models.TextField('E-mail')
    mensagem_enviada = models.TextField('Mensagem Enviada')

    class Meta:
        ordering = ('-data',)
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'

    def __str__(self):
        return f'{self.pk}-{self.get_tipo_display()}'


class ModuloComPendenciaNotificado(models.ModelPlus):
    modulo = models.ForeignKeyPlus(ModuloAprendizagem, verbose_name='Módulo Aprendizagem')
    notificacao = models.ForeignKeyPlus(NotificacaoAprendizagem, verbose_name='Notificação')


class JustificativaVisitaModuloAprendizagem(models.ModelPlus):
    modulo = models.ForeignKeyPlus(ModuloAprendizagem, verbose_name='Módulo Aprendizagem')
    motivos = models.TextField('Informo que a visita à organização concedente não foi realizada pelos seguintes motivos', blank=False)
    outros_acompanhamentos = models.TextField(
        'Foram realizadas outras formas de acompanhamento do (a) aluno (a) sob sua orientação? Se sim, informe quais', blank=True
    )
    formulario_justificativa = models.FileFieldPlus(
        'Formulário de Justificativa',
        help_text='Esse documento deve ser solicitado ao Coordenador de Estágios, preenchido pelo orientador, e assinado pelo (a) Aluno (a) e Coordenador de Curso/Diretor Acadêmico. Limite de tamanho do arquivo de 2MB',
        blank=False,
        upload_to='justificativa_visita_modulo_aprendizagem/relatorio',
        max_file_size=2097152,
    )
    relatorio_interno = models.FileFieldPlus(
        'Relatório de Justificativa de Visita',
        help_text='Relatório gerado pelo sistema após o preenchimento deste formulário.',
        blank=True,
        null=True,
        upload_to='justificativa_visita_moduloaprendizagem/relatorio_interno',
        max_file_size=2097152,
    )
    assinatura_orientador = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Orientador',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_aprendizagem_orientador',
    )
    assinatura_aprendiz = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Aprendiz',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_aprendizagem_aprendiz',
    )
    # Campo descontinuado. Mantido apenas para preservar assinaturas antigas.
    assinatura_coordenador_curso = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Coordenador de Curso',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_aprendizagem_coordenador_curso',
    )
    assinatura_coordenador_extensao = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Coordenador de Extensão',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_aprendizagem_coordenador_extensao',
    )
    assinatura_diretor_academico = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Diretor Acadêmico',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_aprendizagem_diretor_academico',
    )

    def save(self):
        if not self.pk:
            self.notificar_pendencia_assinatura()
        super().save()

    @property
    def aprendizagem(self):
        return self.modulo.aprendizagem

    def pode_assinar(self, user=None):
        user = user or tl.get_user()
        if self.assinatura_orientador is None:
            # Verifica se é orientador.
            # O fluxo termina aqui se não for, pois a assinatura do orientador é pré-requisito para as demais.
            return self.aprendizagem.eh_orientador(user)
        if self.assinatura_coordenador_extensao is None and self.aprendizagem.eh_coordenador_de_extensao(user):
            return True
        if self.assinatura_diretor_academico is None and self.aprendizagem.eh_diretor_academico(user):
            return True
        return bool(self.assinatura_aprendiz is None and self.aprendizagem.eh_aprendiz(user))

    def assinar(self, user, papel):
        if papel == 'Orientador' and self.assinatura_orientador is None and self.aprendizagem.eh_orientador(user):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_orientador = assinatura
        elif (
            papel == 'Coordenador de Extensão' and self.assinatura_coordenador_extensao is None and self.aprendizagem.eh_coordenador_de_extensao(user)
        ):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_coordenador_extensao = assinatura
        elif papel == 'Diretor Acadêmico' and self.assinatura_diretor_academico is None and self.aprendizagem.eh_diretor_academico(user):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_diretor_academico = assinatura
        elif papel == 'Aluno' and self.assinatura_aprendiz is None and self.aprendizagem.eh_aprendiz(user):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_aprendiz = assinatura
        self.save()

    def invalidar_assinaturas(self):
        for assinatura in (
            self.assinatura_aprendiz,
            self.assinatura_orientador,
            self.assinatura_coordenador_curso,
            self.assinatura_coordenador_extensao,
            self.assinatura_diretor_academico,
        ):
            if assinatura is not None:
                assinatura.delete()
        self.refresh_from_db(
            fields=[
                'assinatura_aprendiz',
                'assinatura_orientador',
                'assinatura_coordenador_curso',
                'assinatura_coordenador_extensao',
                'assinatura_diretor_academico',
            ]
        )

    def resetar_documento_eletronico(self):
        self.invalidar_assinaturas()
        self.relatorio_interno.delete()

    def notificar_pendencia_assinatura(self):
        titulo = '[SUAP] Pendência de Assinatura da Justificativa de Decurso de Prazo de Visita de Aprendizagem'
        mensagem = render_to_string(
            template_name='notificacoes/aprendizagem_pendencia_assinatura_justificativa_visita.html',
            context={
                'nome_aprendiz': normalizar_nome_proprio(self.modulo.aprendizagem.aprendiz.get_nome_social_composto()),
                'matricula_aprendiz': self.modulo.aprendizagem.aprendiz.matricula,
                'url_aprendizagem': f'{settings.SITE_URL}{self.modulo.aprendizagem.get_absolute_url()}',
            },
        )
        vinculos = [
            self.aprendizagem.aprendiz.get_vinculo(),
            self.aprendizagem.orientador.vinculo,
            *get_coordenadores_vinculos(get_coordenadores_extensao(self.aprendizagem.aprendiz)),
        ]
        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)
        for vinculo in vinculos:
            if vinculo:
                notificacao = NotificacaoAprendizagem(
                    aprendizagem=self.aprendizagem,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoAprendizagem.NOTIFICACAO_ASSINATURA_DECURSO_PRAZO_PENDENTE,
                    notificador=None,
                    email_destinatario=vinculo.user.email,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def get_assinaturas_pendentes(self, user):
        result = []
        if self.assinatura_orientador is None and self.aprendizagem.eh_orientador(user):
            result.append('Orientador')
        if self.assinatura_orientador:
            if self.assinatura_coordenador_extensao is None and self.aprendizagem.eh_coordenador_de_extensao(user):
                result.append('Coordenador de Extensão')
            if self.assinatura_diretor_academico is None and self.aprendizagem.eh_diretor_academico(user):
                result.append('Diretor Acadêmico')
            if self.assinatura_aprendiz is None and self.aprendizagem.eh_aprendiz(user):
                result.append('Aluno')
        return result


class TipoRemuneracao(models.ModelPlus):
    descricao = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = 'Tipos de Remuneração'
        verbose_name = 'Tipos de Remunerações'

    def __str__(self):
        return self.descricao


class SituacaoAtividade(models.ModelPlus):
    descricao = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = 'Situação de Atividade'
        verbose_name = 'Situações de Atividades'

    def __str__(self):
        return self.descricao


class OfertaPraticaProfissional(models.ModelPlus):
    ESTAGIO = 1
    JOVEM_APRENDIZ = 2

    TIPO_CHOICES = [[ESTAGIO, 'Estágio'], [JOVEM_APRENDIZ, 'Jovem Aprendiz']]

    # Dados gerais
    concedente = models.CharFieldPlus('Concedente', default='')
    data_inicio = models.DateFieldPlus('Início das Inscrições')
    data_fim = models.DateFieldPlus('Fim das Inscrições')

    # Dados da Oferta
    tipo_oferta = models.PositiveIntegerFieldPlus('Tipo da Oferta', choices=TIPO_CHOICES, null=True, blank=False)
    cursos = models.ManyToManyFieldPlus(CursoCampus, verbose_name='Cursos', blank=False)
    a_partir_do_periodo = models.IntegerField('A Partir do Período', blank=True, null=True, choices=[[nota, nota] for nota in range(1, 10 + 1)])
    turno = models.ForeignKeyPlus(
        'edu.Turno',
        verbose_name='Alunos do Turno',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text='Não preencher caso a oferta seja direcionada a alunos de diversos turnos.',
    )
    qtd_vagas = models.IntegerField('Quantidade de Vagas')

    # Carga-Horária
    ch_semanal = models.IntegerField('C.H. Semanal')

    # Outras Informações
    folder = models.FileFieldPlus('Folder Publicitário', null=True, blank=True, max_length=255, upload_to='ofertas/folders')
    habilidades = models.TextField('Habilidades', blank=True)
    descricao_atividades = models.TextField('Descrição das Atividades', blank=True)
    observacoes = models.TextField('Observações', blank=True)

    class Meta:
        verbose_name = 'Oferta de Estágio ou Jovem Aprendiz'
        verbose_name_plural = 'Ofertas de Estágios ou Jovem Aprendiz'

    def __str__(self):
        return f'Oferta de Estágio ou Jovem Aprendiz na Concedente {self.concedente} ({self.qtd_vagas:d} vagas)'

    def get_absolute_url(self):
        return f'/estagios/oferta_pratica_profissional/{self.pk}/'


class PraticaProfissional(models.ModelPlus):
    TIPO_ESTAGIO = 1
    TIPO_ATIVIDADE_PROFISSIONAL = 2
    TIPO_APRENDIZAGEM = 3
    TIPO_CHOICES = [[TIPO_ESTAGIO, 'Estágio'], [TIPO_APRENDIZAGEM, 'Aprendizagem'], [TIPO_ATIVIDADE_PROFISSIONAL, 'Atividade Profissional Efetiva']]

    MOTIVO_CONCLUSAO = 1
    MOTIVO_RESCISAO = 2
    MOTIVO_RESCISAO_MATRICULA_IRREGULAR = 3
    MOTIVO_CHOICES = [[MOTIVO_CONCLUSAO, 'Conclusão'], [MOTIVO_RESCISAO, 'Rescisão']]

    MOTIVO_POR_TERMINO_PREVISTO = 1
    MOTIVO_CONTRATACAO = 2
    MOTIVO_RESCISAO_ESTAGIARIO = 3
    MOTIVO_RESCISAO_CONCEDENTE = 4
    MOTIVO_RESCISAO_INSTITUICAO = 5
    MOTIVACAO_DESLIGAMENTO_ENCERRAMENTO_CHOICHES = [
        [MOTIVO_POR_TERMINO_PREVISTO, 'Por término do período previsto no Termo de Compromisso.'],
        [MOTIVO_CONTRATACAO, 'Contratação do estagiário pela concedente.'],
        [MOTIVO_RESCISAO_ESTAGIARIO, 'Rescisão por iniciativa do estagiário.'],
        [MOTIVO_RESCISAO_CONCEDENTE, 'Rescisão por iniciativa da concedente.'],
        [MOTIVO_RESCISAO_INSTITUICAO, 'Rescisão por iniciativa da instituição de ensino.'],
    ]

    SITUACAO_APROVADO = 1
    SITUACAO_REPROVADO = 2
    SITUACAO_CHOICES = [[SITUACAO_APROVADO, 'Aprovado'], [SITUACAO_REPROVADO, 'Reprovado']]

    CONCEITO_EXCELENTE = 'Excelente'
    CONCEITO_MUITO_BOM = 'Muito Bom'
    CONCEITO_BOM = 'Bom'
    CONCEITO_REGULAR = 'Muito Regular'
    CONCEITO_INSUFICIENTE = 'Insuficiente'
    CONCEITO_CHOICES = [
        [CONCEITO_EXCELENTE, CONCEITO_EXCELENTE],
        [CONCEITO_MUITO_BOM, CONCEITO_MUITO_BOM],
        [CONCEITO_BOM, CONCEITO_BOM],
        [CONCEITO_REGULAR, CONCEITO_REGULAR],
        [CONCEITO_INSUFICIENTE, CONCEITO_INSUFICIENTE],
    ]

    STATUS_EM_ANDAMENTO = 1
    STATUS_COM_PENDENCIA = 2
    STATUS_APTO_PARA_CONCLUSAO = 5
    STATUS_AGUARDANDO_AVALIACAO_ESTAGIARIO = 3
    STATUS_CONCLUIDO = 6
    STATUS_RESCINDIDO = 7
    STATUS_CHOICES = [
        [STATUS_EM_ANDAMENTO, 'Em Andamento/Em Fase Inicial'],
        [STATUS_COM_PENDENCIA, 'Com Pendência'],
        [STATUS_APTO_PARA_CONCLUSAO, 'Apto para Encerramento'],
        [STATUS_CONCLUIDO, 'Encerrado'],
        [STATUS_RESCINDIDO, 'Rescindido'],
    ]

    # Dados gerais
    tipo = models.IntegerField('Tipo', choices=TIPO_CHOICES, default=TIPO_ESTAGIO)
    obrigatorio = models.BooleanField(
        'O estágio é obrigatório', choices=[[False, 'Estágio não-obrigatório'], [True, 'Estágio obrigatório']], blank=True, null=False
    )
    turno = models.ForeignKeyPlus(Turno, verbose_name='Turno', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus(Aluno, verbose_name='Estagiário')
    convenio = models.ForeignKeyPlus(Convenio, verbose_name='Convênio', null=True, blank=True)
    empresa = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Concedente',
        help_text='Para adicionar um concedente de estágio pessoa jurídica acesse: '
        '<strong>Administração -> Cadastros -> Pessoas Júridicas</strong>. '
        'Se for pessoa física, acesse: <strong>Administração -> Cadastros -> '
        'Usuários Externos -> Usuários Externos</strong>.',
    )
    cidade = models.ForeignKeyPlus('edu.Cidade', verbose_name='Município', null=True, on_delete=models.CASCADE, blank=True)
    logradouro = models.CharFieldPlus(null=True, blank=True)
    numero = models.CharField('Nº', max_length=50, null=True, blank=True)
    complemento = models.CharFieldPlus(null=True, blank=True)
    bairro = models.CharFieldPlus(null=True, blank=True)
    cep = models.CharField('CEP', max_length=9, null=True, blank=True)

    representante_concedente = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        verbose_name='Representante da Concedente',
        blank=True,
        on_delete=models.CASCADE,
        related_name='estagio_representante_concedente',
        help_text='Só preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
    )

    nome_representante_concedente = models.CharFieldPlus(
        'Nome do Representante',
        blank=True,
        null=True,
        help_text='Representante da concedente que assinará o '
        'termo de compromisso'
        '. Não preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
    )
    cargo_representante_concedente = models.CharFieldPlus('Cargo do Representante', blank=True, null=True)
    ramo_atividade = models.CharFieldPlus('Ramo de Atividade', blank=True, null=True)
    orientador = models.ForeignKeyPlus(Professor, verbose_name='Professor Orientador')
    servidor_representante = models.ForeignKeyPlus(
        Servidor,
        related_name='estagios_como_servidor_representante_set',
        verbose_name='Servidor Representante da Instituição de Ensino',
        null=True,
        blank=True,
        help_text='Servidor que assinará o Termo de Compromisso em nome da instituição de ensino.',
    )

    # Bolsa
    remunerada = models.BooleanField('Remunerada', default=False)
    tipo_remuneracao = models.ForeignKeyPlus(TipoRemuneracao, verbose_name='Tipo de Remuneração', null=True, blank=True, on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus(verbose_name='Bolsa (R$)', null=True, blank=True)
    auxilio_transporte = models.DecimalFieldPlus(verbose_name='Auxílio Transporte (R$)', null=True, blank=True)
    auxilio_alimentacao = models.DecimalFieldPlus(
        verbose_name='Outros Benefícios (R$)', null=True, blank=True, help_text='Soma de outros benefícios.'
    )
    descricao_outros_beneficios = models.TextField('Descrição', blank=True, help_text='Descrição de outros benefícios recebidos.')

    # Carga Horária
    data_inicio = models.DateFieldPlus('Data de Início')
    data_prevista_fim = models.DateFieldPlus('Data Prevista para Encerramento')
    ch_semanal = models.DecimalField('C.H. Semanal', decimal_places=1, max_digits=3)
    ch_diaria = models.DecimalField('C.H. Diária', decimal_places=1, max_digits=3, null=True, blank=True)
    horario = models.CharFieldPlus(
        'Horário do Estágio',
        help_text='Exemplos: "de segunda a sexta, das 7:30 às 11:30",'
        ' "segunda e quarta, das 7:00 às 12:00 e das 13:00 '
        'às 17:00 e sexta das 8:00 às 12:00". '
        'Esse texto será usado para o preenchimento do '
        'campo horário no Termo de Compromisso gerado pelo '
        'sistema.',
        null=True,
        blank=True,
    )

    # Documentação
    relatorio_avaliacao_instalacoes = models.PrivateFileField(
        'Relatório de avaliação das Instalações ',
        help_text='Relatório previsto no inciso II, artigo 7º, Lei nº 11.788.',
        blank=True,
        max_length=255,
        upload_to='pratica_profissional/relatorio_avaliacao_instalacoes',
    )

    plano_atividades = models.FileFieldPlus('Plano de Atividades', blank=True, max_length=255, upload_to='pratica_profissional/planos_atividades')
    termo_compromisso = models.FileFieldPlus(
        'Termo de Compromisso',
        blank=True,
        max_length=255,
        upload_to='pratica_profissional/termos_compromissos',
        help_text='Caso o documento seja unificado (contenha o Plano de Atividades e o Termo de Compromisso) inserir o arquivo duas vezes.',
    )
    termo_compromisso_documentotexto = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto', null=True, on_delete=models.PROTECT, verbose_name='Termo de Compromisso - Documento Eletrônico'
    )
    documentacao_comprobatoria = models.FileFieldPlus(
        'Documentação Comprobatória', blank=True, max_length=255, upload_to='pratica_profissional/documentacao_comprobatoria'
    )

    # Seguro
    nome_da_seguradora = models.CharFieldPlus('Nome da Seguradora', blank=False, null=True)
    cnpj_da_seguradora = models.BrCnpjField(verbose_name='CNPJ da Seguradora', null=True, blank=True)
    numero_seguro = models.CharFieldPlus('Número da Apólice do Seguro')

    # Supervisor
    nome_supervisor = models.CharFieldPlus(
        'Nome', blank=False, help_text='Não preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.'
    )
    telefone_supervisor = models.CharFieldPlus('Telefone', blank=False)
    cargo_supervisor = models.CharFieldPlus('Cargo', blank=False)
    email_supervisor = models.CharFieldPlus('E-mail', blank=False, help_text='Este e-mail será importante para o envio da avaliação.')
    observacao = models.TextField('Observação', blank=True)
    supervisor = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='estagio_supervisor',
        help_text='Só preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
    )
    # Dados de Encerramento
    data_fim = models.DateFieldPlus('Data do Encerramento', null=True)
    movito_encerramento = models.IntegerField('Encerramento por', null=True, choices=MOTIVO_CHOICES)
    motivacao_desligamento_encerramento = models.IntegerField(
        'Motivação do Desligamento/ Encerramento', null=True, choices=MOTIVACAO_DESLIGAMENTO_ENCERRAMENTO_CHOICHES
    )
    motivo_rescisao = models.TextField(
        'Observações',
        null=True,
        blank=True,
        help_text='Inserir o motivo da rescisão, do encerramento com pendência ou outras informações relevantes.',
    )
    situacao = models.IntegerField('Situação', null=True, blank=True, choices=SITUACAO_CHOICES)
    ch_final = models.IntegerField('C.H. Final', default=0)
    ficha_frequencia = models.FileFieldPlus(
        'Ficha de Frequência', null=True, blank=True, max_length=255, upload_to='pratica_profissional/ficha_frequencia'
    )
    termo_encerramento = models.FileFieldPlus(
        'Termo de Realização de Estágio', null=True, blank=False, max_length=255, upload_to='pratica_profissional/termos_encerramento'
    )
    estagio_anterior_20161 = models.BooleanField(
        'Estágio anterior a 2017.1',
        help_text='Marcar "Sim" caso este estágio não tenha toda a documentação necessária para encerramento e tenha se encerrado até o dia 30/04/2017 (Anterior ao início do ano letivo 2017.1).',
        default=False,
        choices=[[True, 'Sim'], [False, 'Não']],
    )

    # Avaliacao do Estagiário
    data_avaliacao_aluno = models.DateField('Data da Avaliação', null=True)
    contribuiu_formacao = models.BooleanField(
        'Contribuiu para Formação', help_text='As atividades desenvolvidas contribuiram para a sua formação profissional?', default=False
    )
    aplicou_conhecimentos = models.BooleanField(
        'Aplicou Conhecimentos', help_text='Você teve oportunidade de aplicar conhecimentos adquiridos no seu curso?', default=False
    )
    conceito = models.CharFieldPlus('Conceito', choices=CONCEITO_CHOICES, help_text='Qual conceito você atribui ao seu estágio?', default='')
    comentarios = models.TextField(
        'Comentários e Sugestões',
        null=True,
        blank=True,
        help_text='Aqui você pode falar sobre sua experiência de estágio, aprendizado, atividades desenvolvidas na concedente e dar sugestões.',
    )

    # Avaliação do Supervisor
    avaliacao_supervisor = models.FileFieldPlus(
        'Avaliação do Supervisor',
        null=True,
        blank=False,
        max_length=255,
        upload_to='pratica_profissional/avaliacao_supervisor',
        help_text='Esta deve ser a versão original assinada pelo Supervisor',
    )
    data_avaliacao_supervisor = models.DateField('Data da Avaliação', null=True)
    atividades_nao_previstas = models.TextField('Atividades Não-Previstas', blank=True, default='')
    comentarios_supervisor = models.TextField(
        'Comentários do Supervisor',
        null=True,
        blank=False,
        help_text='Aqui o supervisor pode falar sobre a prática do estagiário '
        'em sua concedente e sua experiência recebendo o estagiário e '
        'dar sugestões.',
    )

    status = models.IntegerField('Situação', default=STATUS_EM_ANDAMENTO, choices=STATUS_CHOICES)
    data_atualizacao_situacao = models.DateField('Data da Atualização do Situação', null=True)
    pendente_visita = models.BooleanField('Pendente de Visita?', null=True, blank=True)
    pendente_relatorio_estagiario = models.BooleanField('Pendente de Relatório do Estagiário?', null=True, blank=True)
    pendente_relatorio_supervisor = models.BooleanField('Pendente de Relatório do Supervisor?', null=True, blank=True)
    codigo_verificador = models.TextField(default='')

    # Prazo para regularizar a matrícula
    prazo_final_regularizacao_matricula_irregular = models.DateFieldPlus('Prazo Final para Regularizar a Matrícula', null=True, blank=True)
    desvinculado_matricula_irregular = models.BooleanField(
        'Aluno Desvinculado por Matrícula Irregular', help_text='Selecione para o caso de abandono do aluno.', default=False
    )

    testemunha1 = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Testemunha 1',
        on_delete=models.CASCADE,
        related_name='estagio_testemunha1',
        help_text='Só preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
    )
    testemunha_1 = models.CharFieldPlus(
        'Nome da Testemunha 1',
        null=True,
        blank=True,
        help_text='Testemunha que assinará o termo de compromisso. Não preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
    )

    testemunha2 = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Testemunha 2',
        on_delete=models.CASCADE,
        related_name='estagio_testemunha2',
        help_text='Só preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
    )
    testemunha_2 = models.CharFieldPlus(
        'Nome da Testemunha 2',
        null=True,
        blank=True,
        help_text='Testemunha que assinará o termo de compromisso. Não preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
    )
    agente_integracao = models.ForeignKeyPlus(
        PessoaJuridica, verbose_name='Agente de Integração', null=True, blank=True, related_name='agentes_integracao'
    )

    class History:
        ignore_fields = ('data_atualizacao_situacao',)

    class Meta:
        verbose_name = 'Estágio'
        verbose_name_plural = 'Estágios'

    def __str__(self):
        return f'Estágio de {self.aluno} em {self.empresa}'

    @transaction.atomic()
    def save(self, *args, **kwargs):
        """
        if self.movito_encerramento == self.MOTIVO_RESCISAO:
            self.status = PraticaProfissional.STATUS_RESCINDIDO
            self.notificar()
            super(PraticaProfissional, self).save()
            return

        if self.estagio_anterior_20161 is True:
            self.status = PraticaProfissional.STATUS_CONCLUIDO
            self.notificar()
            super(PraticaProfissional, self).save()
            return

        if somar_data(self.data_inicio, 90) > datetime.date.today():
            self.status = PraticaProfissional.STATUS_EM_ANDAMENTO
        else:
            if self.visitapraticaprofissional_set.exists():
                if self.data_avaliacao_supervisor:
                    if not self.data_avaliacao_aluno:
                        self.status = PraticaProfissional.STATUS_AGUARDANDO_AVALIACAO_ALUNO
                    else:
                        if self.data_fim:
                            self.status = PraticaProfissional.STATUS_CONCLUIDO
                        else:
                            self.status = PraticaProfissional.STATUS_APTO_PARA_CONCLUSAO
                else:
                    self.status = PraticaProfissional.STATUS_AGUARDANDO_RELATORIO_SUPERVISOR
            else:
                self.status = PraticaProfissional.STATUS_AGUARDANDO_VISITA_ORIENTADOR
        if not self.codigo_verificador:
            self.codigo_verificador = hashlib.sha1('{}{}{}'.format(
                self.orientador.pk, datetime.datetime.now(), settings.SECRET_KEY).encode()).hexdigest()
        super(PraticaProfissional, self).save()
        self.notificar()
        """
        desfazer_encerramento = kwargs.pop('desfazer_encerramento', False)
        self.data_atualizacao_situacao = None
        if self.pk:
            self.atualizar_situacoes()
            self.atualiza_status()
            novo_estagio = False
        else:
            novo_estagio = True
        if not self.codigo_verificador:
            self.codigo_verificador = hashlib.sha1(f'{self.orientador.pk}{datetime.datetime.now()}{settings.SECRET_KEY}'.encode()).hexdigest()

        super().save()
        self.gerenciar_atividade_pratica_profissional(novo_estagio, desfazer_encerramento)

    def gerenciar_atividade_pratica_profissional(self, novo_estagio, desfazer_encerramento):
        if AtividadePraticaProfissional.pode_registrar(self.aluno, ModalidadePraticaProfissional.MODALIDADE_PRATICA_ESTAGIO):
            if novo_estagio:
                AtividadePraticaProfissional.registrar_inicio(
                    ModalidadePraticaProfissional.MODALIDADE_PRATICA_ESTAGIO,
                    self.id,
                    type(self),
                    self.aluno.get_ultima_matricula_periodo().id,
                    f'/estagios/pratica_profissional/{self.id}/',
                    f'Estágio em {self.empresa}',
                )
            if self.data_fim:
                atividade = AtividadePraticaProfissional.get(self.id, type(self))
                if atividade:
                    AtividadePraticaProfissional.registrar_conclusao(atividade, self.ch_final)
                else:
                    AtividadePraticaProfissional.registrar_inicio_e_conclusao(
                        ModalidadePraticaProfissional.MODALIDADE_PRATICA_ESTAGIO,
                        self.id,
                        type(self),
                        self.aluno.get_ultima_matricula_periodo(excluir_em_aberto=True).id,
                        self.ch_final,
                        f'/estagios/pratica_profissional/{self.id}/',
                        f'Estágio em {self.empresa}',
                    )
            if desfazer_encerramento:
                AtividadePraticaProfissional.desfazer_conclusao(self.id, type(self))

    @transaction.atomic
    def delete(self, *args, **kwargs):
        AtividadePraticaProfissional.remover_registro(self.id, type(self))
        super().delete(*args, **kwargs)

    def pode_anexar_arquivos(self, user=None):
        return tem_permissao_de_coordenador(user, self.aluno.campus)

    def eh_estagiario(self, user):
        return usuario_possui_cadastro(user) and self.aluno == user.get_relacionamento()

    def eh_orientador(self, user):
        return usuario_possui_cadastro(user) and self.orientador and self.orientador.get_vinculo() == user.get_vinculo()

    def eh_supervisor(self, user):
        return usuario_possui_cadastro(user) and self.supervisor and self.supervisor == user.get_vinculo()

    def eh_representante_concedente(self, user):
        return usuario_possui_cadastro(user) and self.representante_concedente and self.representante_concedente.user == user

    @cached_property
    def _diretores_academicos_responsaveis(self):
        return set(get_diretores_academicos(self.aluno))

    def eh_diretor_academico(self, user):
        return user in self._diretores_academicos_responsaveis

    def eh_coordenador_de_extensao(self, user):
        campus_usuario = get_uo(user)
        return in_group(user, 'Coordenador de Extensão') and campus_usuario == self.aluno.campus

    def ha_pendencia_de_visita(self, data_considerada=None):
        opcional_registro_visita = Configuracao.get_valor_por_chave('estagios', 'opcional_registro_visita')
        if opcional_registro_visita:
            return False
        if not data_considerada:
            data_considerada = datetime.date.today()
        if self.data_fim:
            return False
        periodos_trimestrais = self.get_periodos_trimestrais()
        pendente_visita = False
        for periodo in periodos_trimestrais:
            if periodo['fim'] <= data_considerada:
                if (
                    not self.visitapraticaprofissional_set.filter(data_visita__range=(periodo['inicio'], periodo['fim'])).exists()
                    and not self.justificativavisitaestagio_set.filter(inicio=periodo['inicio'], fim=periodo['fim']).exists()
                ):
                    pendente_visita = True
                    break
        return pendente_visita

    def ha_pendencia_relatorio_supervisor(self, data_considerada=None):
        if not data_considerada:
            data_considerada = datetime.date.today()
        if self.data_fim:
            return False
        periodos_semestrais = self.get_periodos_semestrais()
        pendente_relatorio_supervisor = False
        for periodo in periodos_semestrais:
            if periodo['inicio'] + relativedelta(months=+3, days=-1) <= data_considerada:
                if not self.relatoriosemestralestagio_set.filter(
                    eh_relatorio_do_supervisor=True, inicio=periodo['inicio'], fim=periodo['fim']
                ).exists():
                    pendente_relatorio_supervisor = True
                    break
        return pendente_relatorio_supervisor

    def ha_pendencia_relatorio_estagiario(self, data_considerada=None):
        if not data_considerada:
            data_considerada = datetime.date.today()
        if self.data_fim:
            return False
        periodos_semestrais = self.get_periodos_semestrais()
        pendente_relatorio_estagiario = False
        for periodo in periodos_semestrais:
            if periodo['inicio'] + relativedelta(months=+3, days=-1) <= data_considerada:
                if not self.relatoriosemestralestagio_set.filter(
                    eh_relatorio_do_supervisor=False, inicio=periodo['inicio'], fim=periodo['fim']
                ).exists():
                    pendente_relatorio_estagiario = True
                    break
        return pendente_relatorio_estagiario

    def relatorio_do_periodo_ja_foi_submetido(self, periodo: dict, eh_relatorio_do_supervisor=True, exclude_relatorio_pk=None):
        return (
            self.relatoriosemestralestagio_set.filter(
                inicio=periodo['inicio'],
                fim=periodo['fim'],
                eh_relatorio_do_supervisor=eh_relatorio_do_supervisor,
            )
            .exclude(pk=exclude_relatorio_pk)
            .exists()
        )

    @staticmethod
    def data_inicio_submissao_relatorios(periodo: dict):
        """
        Data para início da submissão de relatórios do período.
        Se o período tiver mais de 3 meses, a submissão pode iniciar após a conclusão do primeiro trimestre.
        Se for inferior a isso, a submissão inicia *após* o fim do período.
        """
        if not periodo.get('inicio') or not periodo.get('fim'):
            raise ValueError(f'Período inválido: {periodo}')
        return min(periodo.get('inicio') + relativedelta(months=3, days=1), periodo.get('fim') + relativedelta(days=1))

    def existe_periodo_no_prazo_para_envio_de_relatorios(self, data_considerada=None):
        if not data_considerada:
            data_considerada = get_datetime_now().date()
        if self.data_fim:
            return False
        return any(periodo.get('inicio_submissao_relatorios') <= data_considerada for periodo in self.get_periodos_semestrais())

    def pode_registrar_relatorio(self, user, eh_relatorio_do_supervisor=True, exclude_relatorio_pk=None):
        if tem_permissao_de_coordenador(user=user, campus=self.aluno.campus):
            return True

        if self.existe_periodo_no_prazo_para_envio_de_relatorios():
            if not (
                user.has_perm('estagios.add_praticaprofissional')
                or self.eh_orientador(user)
                or eh_relatorio_do_supervisor
                and self.eh_supervisor(user)
                or not eh_relatorio_do_supervisor
                and self.eh_estagiario(user)
            ):
                return False

            for periodo in self.get_periodos_semestrais():
                if not self.relatorio_do_periodo_ja_foi_submetido(
                    periodo=periodo, eh_relatorio_do_supervisor=eh_relatorio_do_supervisor, exclude_relatorio_pk=exclude_relatorio_pk
                ):
                    return True

        return False

    def atualizar_situacoes(self, salvar=False):
        existem_rel_eletronicos_sem_assinatura = self.relatoriosemestralestagio_set.filter(
            Q(relatorio=''), Q(assinatura_estagiario=None) | Q(assinatura_orientador=None) | Q(assinatura_supervisor=None)
        ).exists()

        if self.data_fim:
            tem_pendencia = (
                self.pendente_relatorio_supervisor
                or self.pendente_relatorio_estagiario
                or self.pendente_visita
                or existem_rel_eletronicos_sem_assinatura
            )
            if tem_pendencia:
                self.pendente_visita = False
                self.pendente_relatorio_estagiario = False
                self.pendente_relatorio_supervisor = False
                super().save()
            return
        else:
            self.pendente_visita = self.ha_pendencia_de_visita()
            self.pendente_relatorio_supervisor = self.ha_pendencia_relatorio_supervisor()
            self.pendente_relatorio_estagiario = self.ha_pendencia_relatorio_estagiario()
            self.data_atualizacao_situacao = datetime.date.today()
            if (
                not self.pendente_relatorio_estagiario
                and not self.pendente_relatorio_supervisor
                and not self.pendente_visita
                and not existem_rel_eletronicos_sem_assinatura
                and self.data_prevista_fim < datetime.date.today()
            ):
                self.notificar_apto_para_conclusao()
            if salvar:
                super().save()

    def resumo_pendencias(self):
        self.atualizar_situacoes(salvar=True)

        if self.data_fim:
            retorno = 'Encerrado'
            return mark_safe(retorno)

        pendencias = []
        if self.pendente_visita:
            pendencias.append('de visita do orientador')
        if self.pendente_relatorio_estagiario:
            pendencias.append('de relatório do estagiário')
        if self.pendente_relatorio_supervisor:
            pendencias.append('de relatório do supervisor')
        if self.usa_assinatura_eletronica_relatorios:
            qs_assinaturas_pendentes = self.relatoriosemestralestagio_set.filter(
                Q(assinatura_estagiario=None) | Q(assinatura_supervisor=None) | Q(assinatura_orientador=None)
            )
            if qs_assinaturas_pendentes.filter(eh_relatorio_do_supervisor=True).exists():
                pendencias.append('de assinatura de relatório do supervisor')
            if qs_assinaturas_pendentes.filter(eh_relatorio_do_supervisor=False).exists():
                pendencias.append('de assinatura de relatório do estagiário')
        if self.tre_eletronico_foi_cadastrado and bool(self.termo_realizacao_eletronico.signatarios_pendentes):
            pendencias.append('de assinatura do Termo de Realização de Estágio')

        if pendencias:
            pendencias = ', '.join(pendencias)
            retorno = f'Pendências: {pendencias}'
        else:
            retorno = 'Sem Pendências.'
        return mark_safe(retorno)

    resumo_pendencias.short_description = 'Resumo de Pendências'

    @property
    def get_atividades(self):
        atividades = ''
        for atividade in self.atividade_set.all():
            atividades += atividade.descricao + '. '
        return atividades

    @staticmethod
    def registro_visita_obrigatorio():
        return Configuracao.get_valor_por_chave('estagios', 'opcional_registro_visita') != 'True'

    @property
    def requer_acompanhamento_de_visitas(self):
        return not self.data_fim and PraticaProfissional.registro_visita_obrigatorio()

    @property
    def notificar_supervisor(self):
        return not Configuracao.get_valor_por_chave('estagios', 'opcional_notificar_supervisor')

    @property
    def requer_notificar_supervisor(self):
        return self.ha_pendencia_relatorio_supervisor() and self.notificar_supervisor

    def notificar(
        self,
        user=None,
        cadastro_rel_atividades=True,
        assinatura_rel_atividades=True,
        registro_visitas=True,
        matricula_irregular=True,
        assinatura_tre=True,
    ):
        if not self.data_fim:
            if cadastro_rel_atividades:
                self.notificar_avaliacao_semestral_aluno(notificar_se_pendente=True)
                self.notificar_avaliacao_semestral_supervisor(notificar_se_pendente=True)
            if assinatura_rel_atividades:
                self.notificar_pendencias_assinatura_relatorios()
            if registro_visitas:
                self.notificar_visitas_pendentes(user)
            if matricula_irregular:
                self.verificar_matricula_irregular()
            if assinatura_tre:
                self.notificar_signatarios_tre_eletronico()

    def notificar_visitas_pendentes(self, user=None):
        if self.requer_acompanhamento_de_visitas:
            for periodo in self.get_periodos_trimestrais():
                if (
                    datetime.date.today() >= periodo['fim']
                    and not self.visitapraticaprofissional_set.filter(data_visita__range=(periodo['inicio'], periodo['fim'])).exists()
                    and not self.justificativavisitaestagio_set.filter(inicio=periodo['inicio'], fim=periodo['fim']).exists()
                ):
                    titulo = '[SUAP] Pendência de Visita de Orientação de Estágio'
                    mensagem = render_to_string(
                        template_name='notificacoes/estagio_visita_pendente.html',
                        context={
                            'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                            'matricula_aluno': self.aluno.matricula,
                            'inicio_periodo': periodo['inicio'],
                            'fim_periodo': periodo['fim'],
                            'data_inicio': self.data_inicio,
                            'data_prevista_fim': self.data_prevista_fim,
                            'url_estagio': f'{settings.SITE_URL}{self.get_absolute_url()}',
                            'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_estagio'),
                            'versao': 'prazo_expirado',
                        },
                    )

                    send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
                    if self.orientador.vinculo.user.email:
                        notificacao = NotificacaoPendencia(
                            pratica_profissional=self,
                            data=datetime.datetime.now(),
                            tipo=NotificacaoPendencia.NOTIFICACAO_VISITA_TRIMESTRAL,
                            notificador=user,
                            email_destinatario=self.orientador.vinculo.user.email,
                            mensagem_enviada=f'{titulo}<br/>{mensagem}',
                        )
                        notificacao.save()
                        trimestre_notificado = TrimestreNaoVisitadoNotificado(notificacao=notificacao, inicio=periodo['inicio'], fim=periodo['fim'])
                        trimestre_notificado.save()

    def notificar_avaliacao_semestral_supervisor(self, notificar_se_pendente=False, user=None):
        if self.requer_notificar_supervisor:
            periodos_semestrais = self.get_periodos_semestrais()
            semestre = 1
            for periodo in periodos_semestrais:
                if (
                    periodo['fim'] < datetime.date.today()
                    and not self.relatorio_do_periodo_ja_foi_submetido(periodo, eh_relatorio_do_supervisor=True)
                    and (
                        not RelatorioSemestralPendenteNotificado.objects.filter(
                            eh_relatorio_do_supervisor=True,
                            inicio=periodo['inicio'],
                            fim=periodo['fim'],
                            notificacao__pratica_profissional=self,
                            notificacao__data__date__gte=datetime.date.today() + datetime.timedelta(-10),
                        ).exists()
                        or notificar_se_pendente
                    )
                ):
                    url_submissao_relatorio = (
                        f'{settings.SITE_URL}/estagios/avaliar_pratica_profissional_supervisor/'
                        f'?matricula={self.aluno.matricula}'
                        f'&codigo_verificador={self.codigo_verificador[0:6]}'
                        f'&email_supervisor={self.email_supervisor}'
                    )
                    titulo = '[SUAP] Notificação de Avaliação Semestral de Estagiário sob sua Supervisão'
                    mensagem = render_to_string(
                        template_name='notificacoes/estagio_rel_atividades_pendente.html',
                        context={
                            'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                            'matricula_aluno': self.aluno.matricula,
                            'num_periodo': semestre,
                            'inicio_submissao_relatorio': periodo['fim'] + datetime.timedelta(1),
                            'url_submissao_relatorio': url_submissao_relatorio,
                            'url_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_estagio'),
                            'versao': 'supervisor',
                        },
                    )

                    send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.email_supervisor])
                    notificacao = NotificacaoPendencia(
                        pratica_profissional=self,
                        data=datetime.datetime.now(),
                        tipo=NotificacaoPendencia.NOTIFICACAO_RELATORIO_SEMESTRAL_SUPERVISOR,
                        notificador=user,
                        email_destinatario=self.email_supervisor,
                        mensagem_enviada=f'{titulo}<br/>{mensagem}',
                    )
                    notificacao.save()
                    relatorio_pendente_notificado = RelatorioSemestralPendenteNotificado(
                        eh_relatorio_do_supervisor=True, inicio=periodo['inicio'], fim=periodo['fim'], notificacao=notificacao
                    )
                    relatorio_pendente_notificado.save()
                    semestre += 1

    def notificar_avaliacao_semestral_aluno(self, notificar_se_pendente=False, user=None):
        periodos = self.get_periodos_semestrais()
        for periodo in periodos:
            if (
                periodo['fim'] < datetime.date.today()
                and not self.relatorio_do_periodo_ja_foi_submetido(periodo, eh_relatorio_do_supervisor=False)
                and (
                    not RelatorioSemestralPendenteNotificado.objects.filter(
                        eh_relatorio_do_supervisor=False,
                        inicio=periodo['inicio'],
                        fim=periodo['fim'],
                        notificacao__pratica_profissional=self,
                        notificacao__data__date__gte=datetime.date.today() + datetime.timedelta(-10),
                    ).exists()
                    or notificar_se_pendente
                )
            ):
                titulo = '[SUAP] Notificação de Envio de Relatório de Atividades de Estágio'
                mensagem = render_to_string(
                    template_name='notificacoes/estagio_rel_atividades_pendente.html',
                    context={
                        'inicio_periodo': periodo['inicio'],
                        'fim_periodo': periodo['fim'],
                        'inicio_submissao_relatorio': periodo['fim'] + datetime.timedelta(1),
                        'url_estagio': f'{settings.SITE_URL}{self.get_absolute_url()}',
                        'url_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_estagio'),
                        'versao': 'aluno',
                    },
                )

                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])
                email_destinatario = self.get_email_aluno()
                if email_destinatario:
                    notificacao = NotificacaoPendencia(
                        pratica_profissional=self,
                        data=datetime.datetime.now(),
                        tipo=NotificacaoPendencia.NOTIFICACAO_RELATORIO_SEMESTRAL_ALUNO,
                        notificador=user,
                        email_destinatario=email_destinatario,
                        mensagem_enviada=f'{titulo}<br/>{mensagem}',
                    )
                    notificacao.save()
                    relatorio_pendente_notificado = RelatorioSemestralPendenteNotificado(
                        eh_relatorio_do_supervisor=False, inicio=periodo['inicio'], fim=periodo['fim'], notificacao=notificacao
                    )
                    relatorio_pendente_notificado.save()

    def notificar_apto_para_conclusao(self, user=None):
        titulo = '[SUAP] Estágio Apto para Encerramento'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_apto_para_encerramento.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'concedente': str(self.empresa),
                'url_modelos_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_estagio'),
            },
        )

        vinculos = [self.orientador.vinculo, self.aluno.get_vinculo()]
        destinatarios = [self.orientador.vinculo.user.email, self.email_supervisor]
        email_aluno = self.get_email_aluno()
        if email_aluno:
            destinatarios.append(email_aluno)

        if not self.notificacaopendencia_set.filter(tipo=NotificacaoPendencia.NOTIFICACAO_APTO_PARA_CONCLUSAO).exists():
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)
            notificao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_APTO_PARA_CONCLUSAO,
                notificador=user,
                email_destinatario=', '.join(destinatarios),
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def get_email_aluno(self):
        return self.aluno.email_notificacao

    def atualiza_status(self):
        """
        atualizando o status do estágio:

        - se estágio não foi encerrado
            - se tempo do estágio < 3 meses OU (tempo do estágio >= 3 meses E (quant. pendente de visitas - quant. de visitas) > 0)
                aguardando visita do orientador
            - se tempo do estágio < 6 meses OU (tempo do estágio >= 6 meses E (quant. pendente de rel. superv. - quant. de rel. superv.) > 0)
                aguardando relatório do supervisor
            - se tempo do estágio < 6 meses OU (tempo do estágio >= 6 meses E (quant. pendente de rel. estag. - quant. de rel. estag.) > 0)
                aguardando relatório do estagiário
            - se (não está aguardando visita do orientador) E
                 (não está aguardando relatório do supervisor) E
                 (não está aguardando relatório do estagiário)
                - se (quant. esperada de visitas = quant. de visitas) E
                     (quant. esperada de rel. superv. = quant. de rel. superv.) E
                     (quant. esperada de rel. estag. = quant. de rel. estag.)
                    - se foi avaliado pelo estagiário
                        apto para conclusão
                    - senão
                        aguardando avaliação do estagiário
                - senão
                    em andamento
            - senão
                - se aguardando visita do orientador E aguardando relatório do supervisor E aguardando relatório do estagiário
                    aguardando visita do orientador, relatório do supervisor e relatório do estagiário
                - senão se aguardando visita do orientador E aguardando relatório do supervisor
                    aguardando visita do orientador e relatório do supervisor
                - senão se aguardando visita do orientador E aguardando relatório do estagiário
                    aguardando visita do orientador e relatório do estagiário
                - senão se aguardando relatório do supervisor E aguardando relatório do estagiário
                    aguardando relatório do supervisor e relatório do estagiário
                - senão se aguardando visita do orientador
                    aguardando visita do orientador
                - senão se aguardando relatório do supervisor
                    aguardando relatório do supervisor
                - senão se aguardando relatório do estagiário
                    aguardando relatório do estagiário
        - se estágio foi encerrado por motivo de rescisão
            rescindido
        - se estágio foi encerrado E é anterior a 20161
            concluído
        """
        existem_rel_eletronicos_sem_assinatura = self.relatoriosemestralestagio_set.filter(
            Q(relatorio=''), Q(assinatura_estagiario=None) | Q(assinatura_orientador=None) | Q(assinatura_supervisor=None)
        ).exists()

        if not self.data_fim:
            self.status = PraticaProfissional.STATUS_EM_ANDAMENTO
            if self.data_prevista_fim < datetime.date.today() and (
                self.pendente_relatorio_estagiario or self.pendente_relatorio_supervisor or self.pendente_visita
            ):
                self.status = self.STATUS_COM_PENDENCIA

            if (
                not self.pendente_relatorio_estagiario
                and not self.pendente_relatorio_supervisor
                and not existem_rel_eletronicos_sem_assinatura
                and not self.pendente_visita
                and self.data_prevista_fim < datetime.date.today()
            ):
                self.status = self.STATUS_APTO_PARA_CONCLUSAO
                self.notificar_apto_para_conclusao()
        #
        elif self.movito_encerramento == self.MOTIVO_RESCISAO:
            self.status = PraticaProfissional.STATUS_RESCINDIDO  # tem o mesmo o valor de concluído
        elif (
            self.movito_encerramento == self.MOTIVO_CONCLUSAO
            and not self.pendente_relatorio_estagiario
            and not self.pendente_relatorio_supervisor
            and not existem_rel_eletronicos_sem_assinatura
            and not self.pendente_visita
            or self.estagio_anterior_20161
        ):
            self.status = PraticaProfissional.STATUS_CONCLUIDO
        else:
            self.status = PraticaProfissional.STATUS_CONCLUIDO

    @property
    def pode_ser_encerrado(self):
        return self.data_fim is None and (
            not self.tre_eletronico_foi_cadastrado or bool(self.termo_realizacao_eletronico.signatarios_pendentes) is False
        )

    @property
    def registro_de_encerramento_pode_ser_editado(self):
        # O estágio está encerrado sem utilizar a versão eletrônica do Termo de Realização de Estágio
        return self.data_fim is not None and not self.tre_eletronico_foi_cadastrado

    @property
    def foi_rescidido(self):
        return self.movito_encerramento == self.MOTIVO_RESCISAO

    @property
    def is_tempo_estagio_menor_que_3_meses(self):
        return self.get_qtd_dias() < 90

    @property
    def is_tempo_estagio_3_meses_ou_mais(self):
        return not self.is_tempo_estagio_menor_que_3_meses

    @property
    def is_tempo_estagio_menor_que_6_meses(self):
        return self.get_qtd_dias() < 180  # 6 meses = 180 dias

    @property
    def is_tempo_estagio_6_meses_ou_mais(self):
        return not self.is_tempo_estagio_menor_que_6_meses

    @property
    def get_qtd_pendente_visitas_orientador(self):
        qtd = self.get_qtd_esperada_visitas_orientador - self.get_qtd_visitas_orientador
        if qtd < 0:
            qtd = 0
        return qtd

    @property
    def get_qtd_esperada_visitas_orientador(self):
        return self.get_qtd_trimestres()

    @property
    def get_qtd_visitas_orientador(self):
        return self.visitapraticaprofissional_set.all().count()

    @property
    def get_qtd_pendente_relatorios_supervisor(self):
        qtd = self.get_qtd_esperada_relatorios_supervisor - self.get_qtd_relatorios_supervisor
        if qtd < 0:
            qtd = 0
        return qtd

    @property
    def get_qtd_esperada_relatorios_supervisor(self):
        # 6 meses = 180 dias
        # ex: 2 meses = 1 relatório; 6 meses e 1 dia = 2 relatórios; 12 meses = 2 relatórios; 12 meses e dia = 3 relat.
        qtd_dias = self.get_qtd_dias()
        quociente = qtd_dias // 180
        resto = qtd_dias % 180
        if resto:
            return quociente + 1
        return quociente

    @property
    def get_qtd_relatorios_supervisor(self):
        return self.relatoriosemestralestagio_set.filter(eh_relatorio_do_supervisor=True).count()

    @property
    def get_relatorios_supervisor(self):
        return self.relatoriosemestralestagio_set.filter(eh_relatorio_do_supervisor=True).order_by('inicio')

    @property
    def get_nota_media_relatorios_supervisor(self):
        return self.relatoriosemestralestagio_set.filter(eh_relatorio_do_supervisor=True).aggregate(Avg('nota_estagiario'))['nota_estagiario__avg']

    @property
    def get_qtd_pendente_relatorios_estagiario(self):
        qtd_relatorios_pendentes = 0
        for periodo in self.get_periodos_semestrais():
            if periodo['fim'] < datetime.date.today() and not periodo['relatorio_estagiario'].exists():
                qtd_relatorios_pendentes += 1
        return qtd_relatorios_pendentes

    @property
    def get_qtd_esperada_relatorios_estagiario(self):
        return self.get_qtd_esperada_relatorios_supervisor  # idem supervisor

    @property
    def get_qtd_relatorios_estagiario(self):
        return self.relatoriosemestralestagio_set.filter(eh_relatorio_do_supervisor=False).count()

    @property
    def get_relatorios_estagiario(self):
        return self.relatoriosemestralestagio_set.filter(eh_relatorio_do_supervisor=False).order_by('inicio')

    @property
    def usa_assinatura_eletronica_relatorios(self):
        return self.relatoriosemestralestagio_set.filter(relatorio='').exists()

    @property
    def tre_eletronico_foi_cadastrado(self):
        return hasattr(self, 'termo_realizacao_eletronico')

    @property
    def possui_termo_realizacao_estagio(self):
        return self.termo_encerramento or self.tre_eletronico_foi_cadastrado

    @property
    def impediditivos_para_cadastro_do_tre_eletronico(self):
        impeditivos = []
        if self.supervisor is None:
            impeditivos.append('O usuário do(a) Supervisor(a) não foi vinculado ao estágio.')
        if self.representante_concedente is None:
            impeditivos.append('O usuário do(a) Representante da Concedente não foi vinculado ao estágio.')
        return impeditivos

    @property
    def tre_eletronico_pode_ser_cadatrado(self):
        return (
            self.data_fim is None
            and not self.termo_encerramento
            and not self.impediditivos_para_cadastro_do_tre_eletronico
            and not self.tre_eletronico_foi_cadastrado
        )

    @property
    def tre_eletronico_pode_ser_editado(self):
        return self.tre_eletronico_foi_cadastrado and self.termo_realizacao_eletronico.pode_ser_editado

    def tem_permissao_escrita_tre_eletronico(self, user):
        return (
            # usuário é coordenador
            in_group(user, 'Coordenador de Estágio Sistêmico')
            or in_group(user, 'Coordenador de Estágio')
            and get_uo(user) == self.aluno.campus
            # usuário é supervisor
            or self.eh_supervisor(user)
        )

    def pode_assinar_tre_eletronico(self, user):
        return self.tre_eletronico_foi_cadastrado and self.termo_realizacao_eletronico.pode_assinar(user)

    def pode_remover_tre_eletronico(self, user):
        return (
            self.data_fim is None
            and self.tre_eletronico_foi_cadastrado
            and (self.termo_realizacao_eletronico.cadastrado_por == user or self.tem_permissao_escrita_tre_eletronico(user))
        )

    def get_absolute_url(self):
        return f'/estagios/pratica_profissional/{self.pk}/'

    def is_estagio(self):
        return self.tipo == self.TIPO_ESTAGIO

    def is_aprendizagem(self):
        return self.tipo == self.TIPO_APRENDIZAGEM

    def atingiu_data_prevista_fim(self):
        return self.data_prevista_fim <= datetime.date.today()

    def get_datas_limite_para_envio_relatorios_semestrais(self):
        datas_limite = []
        for periodo in self.get_periodos_semestrais():
            datas_limite.append(periodo['fim'])
        return datas_limite

    def get_datas_limite_para_visitas_trimestrais(self):
        datas_limite = []
        for periodo in self.get_periodos_trimestrais():
            datas_limite.append(periodo['fim'])
        return datas_limite

    def get_datas_limite_para_visitas_trimestrais_estagio_menor_180_dias(self):
        delta = self.data_prevista_fim - self.data_inicio
        datas_limite = []
        data_limite = self.data_inicio + datetime.timedelta(delta.days / 2)
        datas_limite.append(data_limite)
        return datas_limite

    def get_qtd_dias(self):
        return (self.data_prevista_fim - self.data_inicio).days + 1

    def get_qtd_meses_e_dias(self):
        return relativedelta(self.data_prevista_fim, self.data_inicio)

    def get_qtd_trimestres(self):
        trimestres = abs(self.get_qtd_dias() / 90)
        if trimestres <= 0:
            trimestres = 1
        return int(trimestres)

    def get_periodos_semestrais(self):
        periodos_semestrais = self.get_periodos()
        for periodo in periodos_semestrais:
            periodo['relatorio_estagiario'] = self.relatoriosemestralestagio_set.filter(
                eh_relatorio_do_supervisor=False, inicio=periodo['inicio'], fim=periodo['fim']
            )
            periodo['relatorio_supervisor'] = self.relatoriosemestralestagio_set.filter(
                eh_relatorio_do_supervisor=True, inicio=periodo['inicio'], fim=periodo['fim']
            )
            periodo['inicio_submissao_relatorios'] = PraticaProfissional.data_inicio_submissao_relatorios(periodo)
        return periodos_semestrais

    def get_periodos_trimestrais(self):
        periodos = self.get_periodos(meses=3)
        if len(periodos) > 1:
            ultimo_periodo = periodos[-1]
            qtd_dias_trimestre = (ultimo_periodo['fim'] - ultimo_periodo['inicio']).days + 1
            if qtd_dias_trimestre < 90:
                periodos = periodos[0:-1]
        for periodo in periodos:
            periodo['visitas'] = self.visitapraticaprofissional_set.filter(data_visita__range=(periodo['inicio'], periodo['fim']))
            periodo['justificativas'] = self.justificativavisitaestagio_set.filter(inicio=periodo['inicio'], fim=periodo['fim'])
        return periodos

    def get_periodos(self, meses=6):
        data_fim = self.data_prevista_fim
        periodos = []
        inicio_prox_periodo = self.data_inicio
        while True:
            fim_prox_periodo = (inicio_prox_periodo + relativedelta(months=+meses)) - datetime.timedelta(1)
            if fim_prox_periodo > data_fim:
                fim_prox_periodo = data_fim
            if inicio_prox_periodo != fim_prox_periodo:
                periodos.append({'inicio': inicio_prox_periodo, 'fim': fim_prox_periodo})
            if fim_prox_periodo != data_fim:
                inicio_prox_periodo = fim_prox_periodo + datetime.timedelta(1)
            else:
                break
        if len(periodos) == 0:
            periodos.append({'inicio': inicio_prox_periodo, 'fim': fim_prox_periodo})
        return periodos

    def get_qtd_relatorios_semestrais_pendentes(self):
        return max(0, len(self.get_periodos_semestrais()) - self.relatoriosemestralestagio_set.count())

    def get_campus(self):
        return f'{self.aluno.curso_campus.diretoria.setor.uo}'

    get_campus.admin_order_field = 'aluno__curso_campus__diretoria__setor__uo'
    get_campus.short_description = 'Campus'

    def get_situacao_convenio(self):
        return f'{self.convenio.situacao.descricao}' if self.convenio else '-'

    get_situacao_convenio.admin_order_field = 'convenio__situacao__descricao'
    get_situacao_convenio.short_description = 'Situação do Convênio'

    def get_situacao_aluno(self):
        return f'{self.aluno.situacao}'

    get_situacao_aluno.admin_order_field = 'aluno__situacao__descricao'
    get_situacao_aluno.short_description = 'Situação do Estagiário'

    def get_situacao_ultima_matricula_periodo(self):
        return f'{self.aluno.get_ultima_matricula_periodo().situacao}'

    get_situacao_ultima_matricula_periodo.admin_order_field = 'aluno__matriculaperiodo__situacao__descricao'
    get_situacao_ultima_matricula_periodo.short_description = 'Situação da Matrícula no Período'

    def get_aditivo(self):
        lista = ['<ul>']
        for aditivo in self.estagioaditivocontratual_set.all():
            lista.append(f'<li>{aditivo}</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_aditivo.short_description = 'Aditivos Contratuais'

    def get_sugestao_ch_final(self):
        dias = numpy.busday_count(self.data_inicio, self.data_prevista_fim + datetime.timedelta(days=1))
        ch_sugerida = dias * (self.ch_semanal / Decimal('5.0'))
        return (
            'Dada a data cadastrada de início e a data prevista para fim deste estágio, considerando-se apenas '
            f'os dias de trabalho (segunda a sexta), estima-se uma carga horária de {format_(ch_sugerida)} horas de trabalho. Deste '
            'total não são excluídos feriados e nem outras possíveis interrupções do trabalho na concedente.'
        )

    def eh_concluido(self):
        return self.status == self.STATUS_CONCLUIDO or self.status == self.STATUS_RESCINDIDO

    def enviar_emails_estagio_recem_cadastrado(self, user=None):
        self.save()
        self.enviar_email_supervisor_recem_cadastrado()

        titulo_orientador = '[SUAP] Cadastro como Orientador de Estágio'
        texto_orientador = render_to_string(
            template_name='notificacoes/estagio_cadastrado.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'nome_orientador': self.orientador.get_nome(),
                'periodos_trimestrais': self.get_periodos_trimestrais(),
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_estagio'),
                'versao': 'orientador',
            },
        )

        send_notification(titulo_orientador, texto_orientador, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_INICIAL,
                notificador=user,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo_orientador}<br/>{texto_orientador}',
            )
            notificacao.save()

        titulo_estagiario = '[SUAP] Cadastro de Estágio'
        texto_estagiario = render_to_string(
            template_name='notificacoes/estagio_cadastrado.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'nome_orientador': self.orientador.get_nome(),
                'periodos_semestrais': self.get_periodos_semestrais(),
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_estagio'),
                'versao': 'aluno',
            },
        )

        send_notification(titulo_estagiario, texto_estagiario, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])
        email_destinatario = self.get_email_aluno()
        if email_destinatario:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_INICIAL,
                notificador=user,
                email_destinatario=email_destinatario,
                mensagem_enviada=f'{titulo_estagiario}<br/>{texto_estagiario}',
            )
            notificacao.save()

    def enviar_email_supervisor_recem_cadastrado(self, user=None):
        titulo_supervisor = '[SUAP] Cadastro como Supervisor de Estágio'
        texto_supervisor = render_to_string(
            template_name='notificacoes/estagio_cadastrado.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'nome_orientador': self.orientador.get_nome(),
                'email_orientador': self.orientador.vinculo.email_notificacao,
                'nome_supervisor': self.nome_supervisor,
                'periodos_semestrais': self.get_periodos_semestrais(),
                'url_portal': Configuracao.get_valor_por_chave('comum', 'url_portal'),
                'url_manuais': Configuracao.get_valor_por_chave('estagios', 'url_manuais_estagio'),
                'versao': 'supervisor',
            },
        )

        send_mail(titulo_supervisor, texto_supervisor, settings.DEFAULT_FROM_EMAIL, [self.email_supervisor])
        notificacao = NotificacaoPendencia(
            pratica_profissional=self,
            data=datetime.datetime.now(),
            tipo=NotificacaoPendencia.NOTIFICACAO_INICIAL,
            notificador=user,
            email_destinatario=self.email_supervisor,
            mensagem_enviada=f'{titulo_supervisor}<br/>{texto_supervisor}',
        )
        notificacao.save()

    def get_periodo_duracao(self):
        if self.data_fim:
            return [self.data_inicio, self.data_fim]
        else:
            return [self.data_inicio, self.data_prevista_fim]

    def verificar_pendencias(self):
        self.verificar_visitas_pendentes()
        self.notificar_avaliacao_semestral_supervisor()
        self.notificar_avaliacao_semestral_aluno()

    def verificar_matricula_irregular(self):
        # se ocorreu matrícula irregular por parte de um aluno
        if self.aluno.situacao in get_situacoes_irregulares() and not self.prazo_final_regularizacao_matricula_irregular:
            self.prazo_final_regularizacao_matricula_irregular = datetime.date.today() + relativedelta(days=7)
            self.save()
            self.notificar_aluno_matricula_irregular()
            self.notificar_supervisor_aluno_matricula_irregular()
            self.notificar_coordenador_aluno_matricula_irregular()
            self.notificar_orientador_aluno_matricula_irregular()

            self.notificar_coordenacao_extensao_aluno_matricula_irregular()
        # se foi dado prazo e o aluno regularizou a matrícula
        if (
            self.aluno.situacao not in get_situacoes_irregulares()
            and self.prazo_final_regularizacao_matricula_irregular
            and not self.notificacaopendencia_set.filter(tipo=NotificacaoPendencia.NOTIFICACAO_FINAL_MATRICULA_IRREGULAR).exists()
        ):
            self.prazo_final_regularizacao_matricula_irregular = None
            self.notificar_supervisor_aluno_matricula_regularizada()
            self.notificar_orientador_aluno_matricula_regularizada()
            self.save()
        # se a situacao irregular persistiu por mais de 7 dias
        if (
            self.aluno.situacao in get_situacoes_irregulares()
            and self.prazo_final_regularizacao_matricula_irregular
            and self.prazo_final_regularizacao_matricula_irregular < datetime.date.today()
            and not self.notificacaopendencia_set.filter(tipo=NotificacaoPendencia.NOTIFICACAO_FINAL_MATRICULA_IRREGULAR).exists()
        ):
            self.notificar_aluno_interrupcao()
            self.notificar_supervisor_interrupcao()
            self.notificar_orientador_interrupcao()

    def notificar_aluno_matricula_irregular(self):
        titulo = '[SUAP] Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_matricula_irregular.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'situacao_aluno': self.aluno.situacao.descricao,
                'curso': self.aluno.curso_campus,
                'data_prevista_fim': self.data_prevista_fim,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                'versao': 'aluno',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])
        email_aluno = self.get_email_aluno()
        if email_aluno:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_supervisor_aluno_matricula_irregular(self):
        titulo = '[SUAP] Notificação de Estagiário com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_matricula_irregular.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nome_supervisor': self.nome_supervisor,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'url_modelos_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_estagio'),
                'versao': 'supervisor',
            },
        )
        if self.email_supervisor:
            send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.email_supervisor])
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.email_supervisor,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_coordenador_aluno_matricula_irregular(self):
        titulo = '[SUAP] Notificação de Estagiário com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_matricula_irregular.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nome_coordenador': self.aluno.curso_campus.coordenador.nome,
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'versao': 'coordenador_do_curso',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.curso_campus.coordenador])
        if self.aluno.curso_campus.coordenador.user.email:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.aluno.curso_campus.coordenador.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_orientador_aluno_matricula_irregular(self):
        titulo = '[SUAP] Notificação de Estagiário com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_matricula_irregular.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nome_orientador': self.orientador.get_nome(),
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'versao': 'orientador',
            },
        )
        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_coordenacao_extensao_aluno_matricula_irregular(self):
        coordenadores = get_coordenadores_estagio(self.aluno)
        coordenadores_emails = get_coordenadores_emails(coordenadores)
        coordenadores_vinculos = get_coordenadores_vinculos(coordenadores)
        titulo = '[SUAP] Notificação de Estagiário com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_matricula_irregular.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nomes_coordenadores': get_coordenadores_nomes(coordenadores),
                'prazo_final_regularizacao_matricula_irregular': self.prazo_final_regularizacao_matricula_irregular,
                'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                'versao': 'coordenacao_de_extensao',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, coordenadores_vinculos)
        if coordenadores_emails:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=coordenadores_emails,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_supervisor_aluno_matricula_regularizada(self):
        titulo = '[SUAP] Notificação de Regularização de Matrícula de Estagiário'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_matricula_regularizada.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nome_supervisor': self.nome_supervisor,
                'data_prevista_fim': self.data_prevista_fim,
                'versao': 'supervisor',
            },
        )
        if self.email_supervisor:
            send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.email_supervisor])
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_REGULARIZADA,
                notificador=None,
                email_destinatario=self.email_supervisor,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_orientador_aluno_matricula_regularizada(self):
        titulo = '[SUAP] Notificação de Regularização de Matrícula de Estagiário'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_matricula_regularizada.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nome_orientador': self.orientador.get_nome(),
                'data_prevista_fim': self.data_prevista_fim,
                'versao': 'orientador',
            },
        )
        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_REGULARIZADA,
                notificador=None,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_pendencias_assinatura_relatorios(self):
        for relatorio in self.relatoriosemestralestagio_set.filter(relatorio=''):
            relatorio.notificar_pendencia_de_assinatura_estagiario()
            relatorio.notificar_pendencia_de_assinatura_orientador()
            relatorio.notificar_pendencia_de_assinatura_supervisor()

    def notificar_orientador_divergencia_relatorios_estagio(self):
        vinculo_orientador = self.orientador.vinculo
        for relatorio_aluno in self.relatoriosemestralestagio_set.filter(eh_relatorio_do_supervisor=False):
            if relatorio_aluno.eh_relatorio_eletronico() and relatorio_aluno.possui_divergencias_com_contraparte():
                titulo = '[SUAP] Notificação: Divergência em Relatórios de Atividades de Estágio'
                mensagem = render_to_string(
                    template_name='notificacoes/estagio_divergencia_rel_atividades.html',
                    context={
                        'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                        'matricula_aluno': self.aluno.matricula,
                        'nome_orientador': self.orientador.get_nome(),
                        'url_estagio': f'{settings.SITE_URL}{self.get_absolute_url()}',
                    },
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_orientador])
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoPendencia.NOTIFICACAO_DIVERGENCIA_RELATORIO_ATIVIDADES,
                    notificador=None,
                    email_destinatario=vinculo_orientador.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()
                break

    def get_data_envio_notificacao(self):
        notificacoes = self.notificacaopendencia_set.filter(tipo=NotificacaoPendencia.NOTIFICACAO_MATRICULA_IRREGULAR).order_by('data')
        if notificacoes.exists():
            return notificacoes[0].data.date()
        else:
            return None

    def notificar_aluno_interrupcao(self):
        titulo = '[SUAP] Notificação de Rescisão/Encerramento de Estágio'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_interrupcao.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'data_envio_notificacao': self.get_data_envio_notificacao(),
                'versao': 'aluno',
            },
        )
        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])
        email_aluno = self.get_email_aluno()
        if email_aluno:
            notificao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_FINAL_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def notificar_supervisor_interrupcao(self):
        coordenadores = get_coordenadores_estagio(self.aluno)
        titulo = '[SUAP] Notificação de Estagiário com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_interrupcao.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nome_supervisor': self.nome_supervisor,
                'emails_coordenadores': get_coordenadores_emails(coordenadores),
                'url_modelos_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_estagio'),
                'versao': 'supervisor',
            },
        )
        if self.email_supervisor:
            send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.email_supervisor])
            notificacao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_FINAL_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.email_supervisor,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def notificar_orientador_interrupcao(self):
        titulo = '[SUAP] Notificação de Estagiário com Matrícula Irregular'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_interrupcao.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                'matricula_aluno': self.aluno.matricula,
                'situacao_aluno': self.aluno.situacao.descricao,
                'nome_orientador': self.orientador.get_nome(),
                'versao': 'orientador',
            },
        )
        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
        if self.orientador.vinculo.user.email:
            notificao = NotificacaoPendencia(
                pratica_profissional=self,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_FINAL_MATRICULA_IRREGULAR,
                notificador=None,
                email_destinatario=self.orientador.vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificao.save()

    def verificar_visitas_pendentes(self, user=None):
        if self.requer_acompanhamento_de_visitas:
            for periodo in self.get_periodos_trimestrais():
                if (
                    datetime.date.today() >= periodo['inicio']
                    and not self.visitapraticaprofissional_set.filter(data_visita__range=(periodo['inicio'], periodo['fim'])).exists()
                    and not self.justificativavisitaestagio_set.filter(inicio=periodo['inicio'], fim=periodo['fim']).exists()
                ):
                    if self.deve_enviar_primeira_notificacao_de_visita_trimestral(periodo):
                        titulo = '[SUAP] Lembrete de Visita de Orientação de Estágio'
                        mensagem = render_to_string(
                            template_name='notificacoes/estagio_visita_pendente.html',
                            context={
                                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                                'matricula_aluno': self.aluno.matricula,
                                'inicio_periodo': periodo['inicio'],
                                'fim_periodo': periodo['fim'],
                                'data_inicio': self.data_inicio,
                                'data_prevista_fim': self.data_prevista_fim,
                                'url_estagio': f'{settings.SITE_URL}{self.get_absolute_url()}',
                                'url_modelos_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_estagio'),
                                'versao': 'lembrete_antecipado',
                            },
                        )

                        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
                        if self.orientador.vinculo.user.email:
                            notificacao = NotificacaoPendencia(
                                pratica_profissional=self,
                                data=datetime.datetime.now(),
                                tipo=NotificacaoPendencia.NOTIFICACAO_VISITA_TRIMESTRAL,
                                notificador=user,
                                email_destinatario=self.orientador.vinculo.user.email,
                                mensagem_enviada=f'{titulo}<br/>{mensagem}',
                            )
                            notificacao.save()
                            trimestre_notificado = TrimestreNaoVisitadoNotificado(
                                notificacao=notificacao, inicio=periodo['inicio'], fim=periodo['fim']
                            )
                            trimestre_notificado.save()
                    elif self.deve_enviar_notificacao_apos_fim_periodo(periodo):
                        titulo = '[SUAP] Pendência de Registro de Visita'
                        mensagem = render_to_string(
                            template_name='notificacoes/estagio_visita_pendente.html',
                            context={
                                'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                                'matricula_aluno': self.aluno.matricula,
                                'inicio_periodo': periodo['inicio'],
                                'fim_periodo': periodo['fim'],
                                'data_inicio': self.data_inicio,
                                'data_prevista_fim': self.data_prevista_fim,
                                'url_estagio': f'{settings.SITE_URL}{self.get_absolute_url()}',
                                'url_modelos_formularios': Configuracao.get_valor_por_chave('estagios', 'url_modelos_formularios_estagio'),
                                'versao': 'prazo_expirado',
                            },
                        )
                        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
                        if self.orientador.vinculo.user.email:
                            notificacao = NotificacaoPendencia(
                                pratica_profissional=self,
                                data=datetime.datetime.now(),
                                tipo=NotificacaoPendencia.NOTIFICACAO_VISITA_TRIMESTRAL,
                                notificador=user,
                                email_destinatario=self.orientador.vinculo.user.email,
                                mensagem_enviada=f'{titulo}<br/>{mensagem}',
                            )
                            notificacao.save()
                            trimestre_notificado = TrimestreNaoVisitadoNotificado(
                                notificacao=notificacao, inicio=periodo['inicio'], fim=periodo['fim']
                            )
                            trimestre_notificado.save()

    def estagio_esta_dentro_do_periodo(self, periodo):
        return datetime.date.today() <= periodo['fim'] and datetime.date.today() >= periodo['inicio']

    def deve_enviar_primeira_notificacao_de_visita_trimestral(self, periodo):
        def dia_envio_inicial_envio(periodo):
            return periodo['inicio'] + (periodo['fim'] - periodo['inicio']) / 3

        def dia_envio_final_envio(periodo):
            return periodo['inicio'] + 2 * (periodo['fim'] - periodo['inicio']) / 3 - relativedelta(days=1)

        return bool(
            periodo['fim'] - relativedelta(days=20) == datetime.date.today()
            and not TrimestreNaoVisitadoNotificado.objects.filter(
                notificacao__pratica_profissional=self,
                inicio=periodo['inicio'],
                fim=periodo['fim'],
                notificacao__data__date__gte=dia_envio_inicial_envio(periodo),
                notificacao__data__date__lt=dia_envio_final_envio(periodo),
            ).exists()
        )

    def deve_enviar_notificacao_apos_fim_periodo(self, periodo):
        return bool(
            datetime.date.today() > periodo['fim']
            and not TrimestreNaoVisitadoNotificado.objects.filter(
                notificacao__pratica_profissional=self,
                inicio=periodo['inicio'],
                fim=periodo['fim'],
                notificacao__data__date__gt=datetime.date.today() + relativedelta(days=-10),
            ).exists()
        )

    def visitas_fora_de_periodo_trimestral(self):
        visitas_em_periodo_trimestral = VisitaPraticaProfissional.objects.none()
        for periodo in self.get_periodos_trimestrais():
            visitas_em_periodo_trimestral |= periodo['visitas']
        return self.visitapraticaprofissional_set.exclude(id__in=visitas_em_periodo_trimestral)

    def notificar_aluno_necessidade_atualizacao_pae(self, data_limite):
        email_aluno = self.get_email_aluno()

        if not NotificacaoPendencia.objects.filter(
            pratica_profissional=self,
            data__range=(data_limite - datetime.timedelta(days=15), data_limite),
            tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
            email_destinatario=email_aluno,
        ).exists():
            titulo = '[SUAP] Notificação: Plano de Atividades de Estágio Precisa ser Atualizado'
            mensagem = render_to_string(
                template_name='notificacoes/estagio_atualizacao_plano_atividades.html',
                context={
                    'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                    'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                    'data_limite': data_limite,
                    'versao': 'aluno',
                },
            )

            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()])

            if email_aluno:
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
                    notificador=None,
                    email_destinatario=email_aluno,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def notificar_supervisor_aluno_necessidade_atualizacao_pae(self, data_limite):
        if not NotificacaoPendencia.objects.filter(
            pratica_profissional=self,
            data__range=(data_limite - datetime.timedelta(days=15), data_limite),
            tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
            email_destinatario=self.email_supervisor,
        ).exists():
            if self.email_supervisor:
                titulo = '[SUAP] Notificação: Plano de Atividades de Estágio Precisa ser Atualizado'
                mensagem = render_to_string(
                    template_name='notificacoes/estagio_atualizacao_plano_atividades.html',
                    context={
                        'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                        'matricula_aluno': self.aluno.matricula,
                        'nome_supervisor': self.nome_supervisor,
                        'data_limite': data_limite,
                        'versao': 'supervisor',
                    },
                )
                send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.email_supervisor])
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
                    notificador=None,
                    email_destinatario=self.email_supervisor,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def notificar_orientador_necessidade_atualizacao_pae(self, data_limite):
        if not NotificacaoPendencia.objects.filter(
            pratica_profissional=self,
            data__range=(data_limite - datetime.timedelta(days=15), data_limite),
            tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
            email_destinatario=self.orientador.vinculo.user.email,
        ).exists():
            titulo = '[SUAP] Notificação: Plano de Atividades de Estágio Precisa ser Atualizado'
            mensagem = render_to_string(
                template_name='notificacoes/estagio_atualizacao_plano_atividades.html',
                context={
                    'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                    'matricula_aluno': self.aluno.matricula,
                    'nome_orientador': self.orientador.get_nome(),
                    'data_limite': data_limite,
                    'versao': 'orientador',
                },
            )
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
            if self.orientador.vinculo.user.email:
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
                    notificador=None,
                    email_destinatario=self.orientador.vinculo.user.email,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def notificar_coordenadores_extensao_necessidade_atualizacao_pae(self, data_limite):
        coordenadores = get_coordenadores_estagio(self.aluno)
        coordenadores_emails = get_coordenadores_emails(coordenadores)

        if not NotificacaoPendencia.objects.filter(
            pratica_profissional=self,
            data__range=(data_limite - datetime.timedelta(days=15), data_limite),
            tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
            email_destinatario=coordenadores_emails,
        ).exists():
            coordenadores_vinculos = get_coordenadores_vinculos(coordenadores)
            titulo = '[SUAP] Notificação: Plano de Atividades de Estágio Precisa ser Atualizado'
            mensagem = render_to_string(
                template_name='notificacoes/estagio_atualizacao_plano_atividades.html',
                context={
                    'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                    'matricula_aluno': self.aluno.matricula,
                    'nomes_coordenadores': get_coordenadores_nomes(coordenadores),
                    'data_limite': data_limite,
                    'versao': 'coordenacao_de_extensao',
                },
            )

            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, coordenadores_vinculos)
            if coordenadores_emails:
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self,
                    data=datetime.datetime.now(),
                    tipo=NotificacaoPendencia.NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE,
                    notificador=None,
                    email_destinatario=coordenadores_emails,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def can_change(self, user):
        return not self.data_fim

    def notificar_orientador_pendencia_visita(self):
        if self.requer_acompanhamento_de_visitas:
            for periodo in self.get_periodos_trimestrais():
                if (
                    (datetime.date.today() + relativedelta(days=20)) == periodo['fim']
                    and not self.visitapraticaprofissional_set.filter(data_visita__range=(periodo['inicio'], periodo['fim'])).exists()
                    and not self.justificativavisitaestagio_set.filter(inicio=periodo['inicio'], fim=periodo['fim']).exists()
                ):
                    titulo = '[SUAP] Pendência de Visita de Orientação de Estágio'
                    mensagem = render_to_string(
                        template_name='notificacoes/estagio_visita_pendente.html',
                        context={
                            'nome_aluno': normalizar_nome_proprio(self.aluno.get_nome_social_composto()),
                            'matricula_aluno': self.aluno.matricula,
                            'inicio_periodo': periodo['inicio'],
                            'fim_periodo': periodo['fim'],
                            'data_inicio': self.data_inicio,
                            'data_prevista_fim': self.data_prevista_fim,
                            'url_estagio': f'{settings.SITE_URL}{self.get_absolute_url()}',
                            'versao': 'prazo_proximo_expiracao',
                        },
                    )

                    send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.orientador.vinculo])
                    if self.orientador.vinculo.user.email:
                        notificacao = NotificacaoPendencia(
                            pratica_profissional=self,
                            data=datetime.datetime.now(),
                            tipo=NotificacaoPendencia.NOTIFICACAO_VISITA_TRIMESTRAL,
                            notificador=None,
                            email_destinatario=self.orientador.vinculo.user.email,
                            mensagem_enviada=f'{titulo}<br/>{mensagem}',
                        )
                        notificacao.save()
                        trimestre_notificado = TrimestreNaoVisitadoNotificado(notificacao=notificacao, inicio=periodo['inicio'], fim=periodo['fim'])
                        trimestre_notificado.save()

    def pode_emitir_declaracao_de_participacao(self):
        user = tl.get_user()
        return self.eh_concluido() and (self.eh_estagiario(user) or tem_permissao_de_coordenador(user, campus=self.aluno.campus))

    def notificar_signatarios_tre_eletronico(self):
        if self.tre_eletronico_foi_cadastrado:
            self.termo_realizacao_eletronico.notificar_pendencia_de_assinatura_estagiario()
            self.termo_realizacao_eletronico.notificar_pendencia_de_assinatura_supervisor()
            self.termo_realizacao_eletronico.notificar_pendencia_de_assinatura_representante_concedente()


class TermoRealizacaoEstagio(models.ModelPlus):
    DESEMPENHO_EXCELENTE = 1
    DESEMPENHO_OTIMO = 2
    DESEMPENHO_BOM = 3
    DESEMPENHO_REGULAR = 4
    DESEMPENHO_INSUFICIENTE = 5
    AVALIACAO_DESEMPENHO_CHOICES = (
        (DESEMPENHO_EXCELENTE, 'Excelente'),
        (DESEMPENHO_OTIMO, 'Ótimo'),
        (DESEMPENHO_BOM, 'Bom'),
        (DESEMPENHO_REGULAR, 'Regular'),
        (DESEMPENHO_INSUFICIENTE, 'Insuficiente'),
    )

    pratica_profissional = models.OneToOneFieldPlus(PraticaProfissional, related_name='termo_realizacao_eletronico')
    data_encerramento = models.DateFieldPlus('Data do encerramento')
    avaliacao_estagiario = models.PositiveSmallIntegerField('Avaliação de desempenho do estagiário', choices=AVALIACAO_DESEMPENHO_CHOICES)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado por', related_name='termos_realizacao_estagio_cadastrados')
    data_cadastro = models.DateTimeFieldPlus('Data do cadastro', auto_now_add=True)

    arquivo_interno = models.PrivateFileField(
        'Arquivo interno do TRE',
        null=True,
        blank=True,
        upload_to='pratica_profissional/termos_realizacao_estagio',
        max_file_size=2097152,
        can_view='pode_visualizar_termo',
    )

    # assinaturas
    assinatura_supervisor = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Supervisor',
        null=True,
        on_delete=models.SET_NULL,
        related_name='termos_realizacao_estagio_como_supervisor',
    )
    assinatura_estagiario = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Estagiário',
        null=True,
        on_delete=models.SET_NULL,
        related_name='termos_realizacao_estagio_como_estagiario',
    )
    assinatura_representante_concedente = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Representante da Concedente',
        null=True,
        on_delete=models.SET_NULL,
        related_name='termos_realizacao_estagio_como_repr_concedente',
    )

    class Meta:
        verbose_name = 'Termo de Realização de Estágio'
        verbose_name_plural = 'Termos de Realização de Estágio'

    @transaction.atomic()
    def delete(self, using=None, keep_parents=False):
        estagio = self.pratica_profissional
        arquivo_obsoleto = self.arquivo_interno
        bem_sucedido, _ = super().delete(using=using, keep_parents=keep_parents)
        if bem_sucedido:
            estagio.movito_encerramento = None
            estagio.motivacao_desligamento_encerramento = None
            estagio.motivo_rescisao = None
            estagio.ch_final = 0
            estagio.save()
            arquivo_obsoleto.delete(save=False)

    def pode_visualizar_termo(self, user=None):
        user = user or tl.get_user()
        vinculo = user.get_vinculo()
        return (
            user.has_perm('estagios.view_termorealizacaoestagio')
            or vinculo is not None
            and vinculo
            in (
                self.pratica_profissional.supervisor,
                self.pratica_profissional.aluno.get_vinculo(),
                self.pratica_profissional.representante_concedente,
            )
        )

    @property
    def url_do_arquivo(self):
        return self.arquivo_interno.url

    @property
    def pode_ser_editado(self):
        return self.assinatura_supervisor is None

    @property
    def situacao_assinaturas(self):
        return (
            ('Supervisor(a)', self.assinatura_supervisor is not None),
            ('Estagiário(a)', self.assinatura_estagiario is not None),
            ('Representante da Concedente', self.assinatura_representante_concedente is not None),
        )

    @property
    def signatarios_pendentes(self):
        if self.assinatura_supervisor is None:
            return [self.pratica_profissional.supervisor]
        vinculos = []
        if self.assinatura_estagiario is None:
            vinculos.append(self.pratica_profissional.aluno.get_vinculo())
        if self.assinatura_representante_concedente is None:
            vinculos.append(self.pratica_profissional.representante_concedente)
        return vinculos

    @property
    def possui_assinatura(self):
        return len(self.signatarios_pendentes) < 3

    def pode_assinar(self, user=None):
        user = user or tl.get_user()
        return usuario_possui_cadastro(user) and user.get_vinculo() in self.signatarios_pendentes

    def assinar(self, user):
        vinculo = user.get_vinculo()
        vinculo_supervisor = self.pratica_profissional.supervisor
        vinculo_estagiario = self.pratica_profissional.aluno.get_vinculo()
        vinculo_representante_concedente = self.pratica_profissional.representante_concedente
        if vinculo in (vinculo_supervisor, vinculo_estagiario, vinculo_representante_concedente):
            assinatura = AssinaturaEletronica(vinculo=vinculo)
            assinatura.assinar()
            if vinculo == vinculo_supervisor:
                self.assinatura_supervisor = assinatura
            if vinculo == vinculo_estagiario:
                self.assinatura_estagiario = assinatura
            if vinculo == vinculo_representante_concedente:
                self.assinatura_representante_concedente = assinatura
            self.save()

            if self.arquivo_interno:
                self.arquivo_interno.delete()

    # Notificações
    def _notificar_pendencia_de_assinatura(self, assinatura_necessaria, vinculo, contexto_mensagem):
        if assinatura_necessaria is None and vinculo in self.signatarios_pendentes:
            # evita envios repetitivos num curto período
            if not NotificacaoPendencia.objects.filter(
                pratica_profissional=self.pratica_profissional,
                tipo=NotificacaoPendencia.NOTIFICACAO_ASSINATURA_TERMO_REALIZACAO_ESTAGIO,
                email_destinatario=vinculo.email_notificacao,
                data__gte=get_datetime_now() - timedelta(days=1),
            ).exists():
                titulo = '[SUAP] Notificação: Pendência de assinatura em Termo de Realização de Estágio'
                mensagem = render_to_string(
                    template_name='notificacoes/estagio_pendencia_assinatura_termo_realizacao_estagio.html',
                    context=contexto_mensagem,
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo])
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self.pratica_profissional,
                    data=get_datetime_now(),
                    tipo=NotificacaoPendencia.NOTIFICACAO_ASSINATURA_TERMO_REALIZACAO_ESTAGIO,
                    notificador=None,
                    email_destinatario=vinculo.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def notificar_pendencia_de_assinatura_estagiario(self):
        vinculo_estagiario = self.pratica_profissional.aluno.get_vinculo()
        url_estagio = f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}?tab=encerramento'
        contexto_mensagem = {
            'nome_aluno': normalizar_nome_proprio(self.pratica_profissional.aluno.get_nome()),
            'url_estagio': url_estagio,
            'versao': 'aluno',
        }

        self._notificar_pendencia_de_assinatura(self.assinatura_estagiario, vinculo_estagiario, contexto_mensagem)

    def notificar_pendencia_de_assinatura_supervisor(self):
        vinculo_supervisor = self.pratica_profissional.supervisor
        url_estagio = f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}?tab=encerramento'
        contexto_mensagem = {
            'nome_supervisor': normalizar_nome_proprio(self.pratica_profissional.supervisor.nome),
            'nome_aluno': normalizar_nome_proprio(self.pratica_profissional.aluno.get_nome()),
            'url_estagio': url_estagio,
            'versao': 'supervisor',
        }

        self._notificar_pendencia_de_assinatura(self.assinatura_supervisor, vinculo_supervisor, contexto_mensagem)

    def notificar_pendencia_de_assinatura_representante_concedente(self):
        vinculo_representante_concedente = self.pratica_profissional.representante_concedente
        url_estagio = f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}?tab=encerramento'
        contexto_mensagem = {
            'nome_representante_concedente': normalizar_nome_proprio(vinculo_representante_concedente.nome),
            'nome_aluno': normalizar_nome_proprio(self.pratica_profissional.aluno.get_nome()),
            'url_estagio': url_estagio,
            'versao': 'representante_concedente',
        }

        self._notificar_pendencia_de_assinatura(self.assinatura_representante_concedente, vinculo_representante_concedente, contexto_mensagem)


# (COLOCAR PRAZOS PARA RELATÓRIOS)
# Manual do Supervisor: http://portal.ifrn.edu.br/extensao/estagios-e-egressos/estagios/manuais-de-utilizacao-do-suap
# Caso necessite entrar em contato conosco basta buscar o telefone do campus na página: www.ifrn.edu.br ou no termo de compromisso de estágio, ou, ainda, entrar em contato com o professor orientador, através do seguinte e-mail: (EMAIL DO PROFESSOR ORIENTADOR).

# Desde já agradecemos pela sua contribuição na formação do nosso aluno'


class AnexoPraticaProfissional(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', null=False, blank=False, max_length=255)
    arquivo = models.FileFieldPlus('Arquivo', blank=False, max_length=255, upload_to='pratica_profissional/anexos')

    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', related_name='%(class)s_usuario_set', on_delete=models.CASCADE)

    class Meta:
        abstract = True
        ordering = ['data_hora']
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'


class AnexoPraticaProfissionalGenerica(AnexoPraticaProfissional):
    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional')

    class Meta(AnexoPraticaProfissional.Meta):
        pass

    def save(self):
        super().save()
        self.pratica_profissional.save()


class AnexoAprendizagem(AnexoPraticaProfissional):
    aprendizagem = models.ForeignKeyPlus(Aprendizagem, verbose_name='Aprendizagem')

    class Meta(AnexoPraticaProfissional.Meta):
        pass

    def save(self):
        super().save()
        self.aprendizagem.save()


class Atividade(models.ModelPlus):
    CONCEITO_EXCELENTE = 1
    CONCEITO_OTIMO = 2
    CONCEITO_BOM = 3
    CONCEITO_REGULAR = 4
    CONCEITO_RUIM = 5
    CONCEITO_CHOICES = [
        [CONCEITO_EXCELENTE, 'Excelente'],
        [CONCEITO_OTIMO, 'Ótimo'],
        [CONCEITO_BOM, 'Bom'],
        [CONCEITO_REGULAR, 'Regular'],
        [CONCEITO_RUIM, 'Ruim'],
    ]

    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional')
    descricao = models.CharFieldPlus('Descrição', default='', width='800', max_length=1024)

    # FIXME: esses dois próximos atributos servem pra quê? avaliação final do estagiário???
    situacao = models.ForeignKeyPlus(SituacaoAtividade, verbose_name='Situação', null=True, on_delete=models.CASCADE)
    conceito = models.IntegerField('Conceito', choices=CONCEITO_CHOICES, null=True, blank=False)

    class Meta:
        verbose_name = 'Atividade do Estágio'
        verbose_name_plural = 'Relação de Atividades do Estágio'
        ordering = ('pk',)

    def __str__(self):
        return f'{self.pk}'


class EstagioAditivoContratual(models.ModelPlus):
    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional')
    descricao = models.CharFieldPlus('Descrição', default='', width='800', max_length=1024, blank=True, null=True)
    aditivo = models.FileFieldPlus('Aditivo', blank=False, max_length=255, upload_to='pratica_profissional/aditivo')
    inicio_vigencia = models.DateFieldPlus('Início da Vingência', blank=False)
    historico = models.TextField('Histórico', null=True)
    tipos_aditivo = models.ManyToManyField('estagios.TipoAditivo', verbose_name='Tipos de Aditivo Contratual', blank=False)

    class Meta:
        verbose_name = 'Aditivo Contratual de Estágio'
        verbose_name_plural = 'Aditivos Contratuais de Estágios'

    def __str__(self):
        lista = []
        for tipo_aditivo in self.tipos_aditivo.all():
            lista.append(str(tipo_aditivo))
        return 'Descrição: {} <br>Tipos: {}'.format(self.descricao, ', '.join(lista))

    def save(self):
        super().save()
        self.pratica_profissional.save()


class TipoAditivo(models.ModelPlus):
    PROFESSOR_ORIENTADOR = 1
    REMUNERACAO = 2
    TRANSPORTE = 3
    OUTROS_BENEFICIOS = 4
    TEMPO = 5
    CARGA_HORARIA = 6
    PLANO_DE_ATIVIDADE = 7
    SUPERVISOR = 8
    HORARIO = 9
    SEGURO = 10
    descricao = models.CharFieldPlus('Decrição')

    class Meta:
        verbose_name = 'Tipo de Aditivo Contratual'
        verbose_name_plural = 'Tipos de Aditivo Contratual'

    def __str__(self):
        return f'{self.descricao}'


class VisitaPraticaProfissional(models.ModelPlus):
    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional')
    orientador = models.ForeignKeyPlus(Professor, verbose_name='Orientador')
    data_visita = models.DateFieldPlus('Data da Visita')
    ambiente_adequado = models.BooleanField(
        'Ambiente Adequado', default=False, help_text='O ambiente de trabalho está adequado ao desenvolvimento das atividades do estagiário?'
    )
    ambiente_adequado_justifique = models.TextField(
        'Justificativa para Ambiente Inadequado',
        default='',
        blank=True,
        help_text='Preencher somente em caso de resposta negativa ao quesito anterior.',
    )
    desenvolvendo_atividades_previstas = models.BooleanField(
        'Desenvolvimento Atividades Previstas',
        default=False,
        help_text='O estagiário está desenvolvendo as atividades previstas no plano de atividades cadastrado no TCE?',
    )
    desenvolvendo_atividades_nao_previstas = models.BooleanField(
        'Desenvolvimento Atividades Não-Previstas',
        default=False,
        help_text='Existem atividades que estão sendo desenvolvidas (da competência do estagiário), mas que não estão previstas no TCE?',
    )
    desenvolvendo_atividades_fora_competencia = models.BooleanField(
        'Desenvolvimento Atividades Fora da Competência',
        default=False,
        help_text='Existem atividades que estão sendo desenvolvidas fora das competências do estagiário?',
    )
    atividades_nao_previstas = models.TextField(
        'Atividades Não-Previstas',
        help_text='Descreva as atividades desenvolvidas que não foram '
        'previstas no plano de atividades, informando ao setor '
        'responsável no IFRN a necessidade da sua atualização.',
        blank=True,
    )
    apoiado_pelo_supervidor = models.BooleanField(
        'Apoiado pelo Supervisor',
        default=False,
        help_text='O estagiário está sendo apoiado/orientado/supervisionado pelo supervisor de estágio da concedente?',
    )
    direitos_respeitados = models.BooleanField(
        'Direitos Respeitados',
        default=False,
        help_text='Os pagamentos de bolsa e auxílio transporte, bem como o horário de trabalho estão sendo respeitados?',
    )
    direitos_respeitados_especificar = models.TextField(
        'Especificar direitos não respeitados',
        default='',
        blank=True,
        help_text='Preencher somente em caso de resposta negativa ao quesito anterior.',
    )
    aprendizagem_satisfatoria = models.BooleanField(
        'Aprendizagem Satisfatória',
        default=False,
        help_text='De um modo geral, quanto à contribuição ao aprendizado '
        'do estagiário, a prática profissional está ocorrendo de forma satisfatória?',
    )
    informacoes_adicionais = models.TextField(
        'Informações Adicionais',
        help_text='O espaço abaixo é reservado ao registro de informações que '
        'considerar relevantes. (ex.: caso alguma questão não tenha '
        'sido respondida, justificar; ou fazer o relato de outras '
        'informações colhidas durante a visita.)',
        blank=True,
    )
    relatorio = models.FileFieldPlus(
        'Relatório de Visita',
        help_text='Inserir o relatório de visita devidamente assinado. Obs.: Este relatório pode ser gerado pelo sistema após o preenchimento deste formulário. Limite de tamanho do arquivo 2MB.',
        blank=False,
        null=True,
        upload_to='visita_pratica_profissional/relatorio',
        max_file_size=2097152,
    )
    ultimo_editor = models.ForeignKeyPlus('comum.User', verbose_name='Último Usuário a Editar', null=True)
    relatorio_interno = models.FileFieldPlus(
        'Relatório de Visita Gerado',
        help_text='Relatório gerado pelo sistema após o preenchimento deste formulário.',
        blank=True,
        null=True,
        upload_to='visita_pratica_profissional/relatorio_interno',
        max_file_size=2097152,
    )
    assinatura_orientador = models.ForeignKeyPlus(
        'AssinaturaEletronica', verbose_name='Assinatura Eletrônica do Orientador', null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = 'Visita do Orientador'
        verbose_name_plural = 'Visitas do Orientador'

    def __str__(self):
        return f'Visita realizada em {format_(self.data_visita)}'

    def save(self):
        super().save()
        self.pratica_profissional.save()

    def get_periodo_trimestral(self):
        periodos = self.pratica_profissional.get_periodos_trimestrais()
        for periodo in periodos:
            if self.data_visita >= periodo['inicio'] and self.data_visita <= periodo['fim']:
                return periodo
        return None

    def can_delete(self, user=None):
        if user is None:
            return False
        is_administrador = user.has_group_cached(['Coordenador de Estágio Sistêmico', 'estagios Administrador'])
        is_coordenador = user.has_group_cached('Coordenador de Estágio') and self.pratica_profissional.aluno.campus == user.get_vinculo().setor.uo
        is_orientador = self.orientador.vinculo == user.get_vinculo()
        return is_administrador or is_coordenador or is_orientador


class RelatorioSemestralEstagio(models.ModelPlus):
    AVALICAO_CONCEITO_EXCELENTE = 1
    AVALICAO_CONCEITO_BOM = 2
    AVALICAO_CONCEITO_REGULAR = 3
    AVALICAO_CONCEITO_RUIM = 4
    AVALICAO_CONCEITO_PESSIMO = 5
    AVALICAO_CONCEITO_CHOICES = [
        [AVALICAO_CONCEITO_EXCELENTE, 'Excelente'],
        [AVALICAO_CONCEITO_BOM, 'Bom'],
        [AVALICAO_CONCEITO_REGULAR, 'Regular'],
        [AVALICAO_CONCEITO_RUIM, 'Ruim'],
        [AVALICAO_CONCEITO_PESSIMO, 'Péssimo'],
    ]

    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional')
    eh_relatorio_do_supervisor = models.BooleanField(editable=False, default=True)

    # data e período do relatório
    data_relatorio = models.DateFieldPlus('Data do Relatório', blank=False, null=True)
    inicio = models.DateFieldPlus('Data Inicial do Período', blank=False, null=True)
    fim = models.DateFieldPlus('Data Final do Período', blank=False, null=True)

    # plano de atividades
    comentarios_atividades = models.TextField('Comentários sobre o desenvolvimento das atividades', null=True, blank=True)
    realizou_outras_atividades = models.BooleanField('Realizou atividades não previstas no Plano de Atividades?', default=False)
    outras_atividades = models.TextField('Em caso afirmativo, descreva as atividades', blank=True, null=True)
    outras_atividades_justificativa = models.TextField('Em caso afirmativo, justifique', blank=True, null=True)

    # relação teoria/prática (somente relatório do estagiário)
    estagio_na_area_formacao = models.BooleanField(
        'Área de Formação',
        help_text='O estágio foi/está sendo desenvolvido em sua área de formação?',
        choices=[[True, 'Sim'], [False, 'Não']],
        null=True,
        blank=True,
    )
    estagio_contribuiu = models.BooleanField(
        'Contribuição do Estágio',
        help_text='As atividades desenvolvidas contribuíram para a sua formação?',
        choices=[[True, 'Sim'], [False, 'Não']],
        null=True,
        blank=True,
    )
    aplicou_conhecimento = models.BooleanField(
        'Aplicação do Conhecimento',
        help_text='Você teve oportunidade de aplicar os conhecimentos adquiridos no seu Curso?',
        choices=[[True, 'Sim'], [False, 'Não']],
        null=True,
        blank=True,
    )

    # avaliação do estágio (somente relatório do estagiário)
    avaliacao_conceito = models.IntegerField(
        'Conceito', help_text='Qual conceito você atribui ao seu estágio no período?', choices=AVALICAO_CONCEITO_CHOICES, null=True, blank=True
    )

    avaliacao_comentarios = models.TextField('Comentários e Sugestões', null=True, blank=True)

    # avaliação de desempenho do estagiário(somente supervisor)
    nota_estagiario = models.IntegerField(
        'Nota do Estagiário',
        choices=[[nota, nota] for nota in range(10 + 1)],
        null=True,
        blank=False,
        help_text='Dê uma nota ao estagiário que avalie seu desempenho como um todo de 0 a 10.',
    )

    # upload do arquivo do relatório
    relatorio = models.FileFieldPlus(
        'Relatório Semestral',
        blank=True,
        null=True,
        upload_to='relatorio_semestral_estagio/relatorio',
        max_file_size=2097152,
        help_text='O relatório semestral deve estar assinado pelo Orientador, Estagiário e Supervisor. Tamanho máximo permitido 2MB. '
        'Ao anexar o arquivo, o relatório não poderá ser assinado eletronicamente.',
        can_view='can_view_relatorio',
    )

    ultimo_editor = models.ForeignKeyPlus('comum.User', verbose_name='Último Usuário a Editar', null=True)

    relatorio_interno = models.FileFieldPlus(
        'Relatório Semestral',
        help_text='Relatório gerado pelo sistema após o preenchimento deste formulário.',
        blank=True,
        null=True,
        upload_to='relatorio_semestral_estagio/relatorio_interno',
        max_file_size=2097152,
    )

    # assinaturas
    assinatura_estagiario = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Estagiário',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='relatorios_estagiario',
    )
    assinatura_orientador = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Orientador',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='relatorios_orientador',
    )
    assinatura_supervisor = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Supervisor',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='relatorios_supervisor',
    )

    class Meta:
        verbose_name = 'Relatório de Atividades'
        verbose_name_plural = 'Relatório de Atividades'

    def __str__(self):
        return f'Relatório Semestral ({self.pk})'

    def save(self):
        super().save()
        self.pratica_profissional.save()

    def can_view_relatorio(self, user):
        if user.has_perm('estagios.view_praticaprofissional'):
            return True

        return (
            self.pratica_profissional.eh_estagiario(user)
            or self.pratica_profissional.eh_orientador(user)
            or self.pratica_profissional.eh_supervisor(user)
        )

    def pode_editar(self, user):
        return self.pratica_profissional.pode_registrar_relatorio(
            user=user, eh_relatorio_do_supervisor=self.eh_relatorio_do_supervisor, exclude_relatorio_pk=self.pk
        )

    def can_delete(self, user=None):
        return not self.pratica_profissional.data_fim

    def eh_relatorio_eletronico(self):
        return not self.relatorio

    def get_situacao_assinaturas(self):
        return (
            ('Estagiário(a)', self.assinatura_estagiario is not None),
            ('Supervisor(a)', self.assinatura_supervisor is not None),
            ('Orientador(a)', self.assinatura_orientador is not None),
        )

    def pode_assinar(self, user=None):
        user = user or tl.get_user()
        if self.pratica_profissional.eh_estagiario(user) and not self.assinatura_estagiario:
            return True
        if self.pratica_profissional.eh_orientador(user) and not self.assinatura_orientador:
            return True
        return bool(self.pratica_profissional.eh_supervisor(user) and not self.assinatura_supervisor)

    def assinar(self, user):
        vinculo = user.get_vinculo()
        assinatura = AssinaturaEletronica(vinculo=vinculo)
        assinatura.assinar()
        if self.pratica_profissional.eh_estagiario(user):
            self.assinatura_estagiario = assinatura
        if self.pratica_profissional.eh_orientador(user):
            self.assinatura_orientador = assinatura
        if self.pratica_profissional.eh_supervisor(user):
            self.assinatura_supervisor = assinatura
        self.save()

    def resetar_relatorio_eletronico(self):
        self.invalidar_assinaturas()
        self.relatorio_interno.delete()

    def invalidar_assinaturas(self):
        for assinatura in (self.assinatura_estagiario, self.assinatura_orientador, self.assinatura_supervisor):
            if assinatura is not None:
                assinatura.delete()
        self.refresh_from_db(fields=['assinatura_estagiario', 'assinatura_orientador', 'assinatura_supervisor'])

    @property
    def relatorio_contraparte(self):
        return RelatorioSemestralEstagio.objects.filter(
            pratica_profissional=self.pratica_profissional,
            inicio=self.inicio,
            fim=self.fim,
            eh_relatorio_do_supervisor=not self.eh_relatorio_do_supervisor,
        ).first()

    def possui_divergencias_com_contraparte(self):
        """
        Verifica se relatório do aluno possui divergências com o do supervisor, e vice-versa.
        """
        from .utils import get_divergencias_relatorios_estagio

        rel_aluno = self if not self.eh_relatorio_do_supervisor else self.relatorio_contraparte
        rel_supervisor = self if self.eh_relatorio_do_supervisor else self.relatorio_contraparte

        return bool(get_divergencias_relatorios_estagio(rel_aluno, rel_supervisor))

    def pode_resolver_divergencias(self, user):
        return self.pratica_profissional.eh_orientador(user) and self.pratica_profissional.existe_periodo_no_prazo_para_envio_de_relatorios()

    def pode_coletar_assinaturas_eletronicas(self):
        return self.eh_relatorio_eletronico() and self.relatorio_contraparte and not self.possui_divergencias_com_contraparte()

    # Notificações
    def notificar_pendencia_de_assinatura_estagiario(self):
        if self.pode_coletar_assinaturas_eletronicas() and not self.assinatura_estagiario:
            vinculo_aluno = self.pratica_profissional.aluno.get_vinculo()
            tipo_notificacao = (
                NotificacaoPendencia.NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_SUPERVISOR
                if self.eh_relatorio_do_supervisor
                else NotificacaoPendencia.NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_ALUNO
            )
            # evita envios repetitivos num curto período
            if not NotificacaoPendencia.objects.filter(
                pratica_profissional=self.pratica_profissional,
                tipo=tipo_notificacao,
                email_destinatario=vinculo_aluno.email_notificacao,
                data__gte=datetime.datetime.now() - timedelta(hours=1),
            ).exists():
                url_relatorios = (
                    f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}'
                    f'?tab={"avaliacaosupervisor" if self.eh_relatorio_do_supervisor else "relatorios"}'
                )
                if self.eh_relatorio_do_supervisor:
                    descricao_relatorio = 'Relatório de Atividades de Estágio do seu supervisor'
                else:
                    descricao_relatorio = 'seu Relatório de Atividades de Estágio'

                titulo = '[SUAP] Notificação: Pendência de Assinatura em Relatório de Atividades de Estágio'
                mensagem = render_to_string(
                    template_name='notificacoes/estagio_pendencia_assinatura_relatorio.html',
                    context={
                        'nome_aluno': normalizar_nome_proprio(self.pratica_profissional.aluno.get_nome_social_composto()),
                        'descricao_relatorio': descricao_relatorio,
                        'url_relatorios': url_relatorios,
                        'versao': 'aluno',
                    },
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_aluno])
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self.pratica_profissional,
                    data=datetime.datetime.now(),
                    tipo=tipo_notificacao,
                    notificador=None,
                    email_destinatario=vinculo_aluno.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def notificar_pendencia_de_assinatura_orientador(self):
        if self.pode_coletar_assinaturas_eletronicas() and not self.assinatura_orientador:
            vinculo_orientador = self.pratica_profissional.orientador.get_vinculo()
            tipo_notificacao = (
                NotificacaoPendencia.NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_SUPERVISOR
                if self.eh_relatorio_do_supervisor
                else NotificacaoPendencia.NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_ALUNO
            )
            # evita envios repetitivos num curto período
            if not NotificacaoPendencia.objects.filter(
                pratica_profissional=self.pratica_profissional,
                tipo=tipo_notificacao,
                email_destinatario=vinculo_orientador.email_notificacao,
                data__gte=datetime.datetime.now() - timedelta(hours=1),
            ).exists():
                url_relatorios = (
                    f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}'
                    f'?tab={"avaliacaosupervisor" if self.eh_relatorio_do_supervisor else "relatorios"}'
                )

                titulo = '[SUAP] Notificação: Pendência de Assinatura em Relatório de Atividades de Estágio'
                mensagem = render_to_string(
                    template_name='notificacoes/estagio_pendencia_assinatura_relatorio.html',
                    context={
                        'nome_aluno': normalizar_nome_proprio(self.pratica_profissional.aluno.get_nome_social_composto()),
                        'matricula_aluno': self.pratica_profissional.aluno.matricula,
                        'nome_orientador': vinculo_orientador.nome,
                        'url_relatorios': url_relatorios,
                        'versao': 'orientador',
                    },
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_orientador])
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self.pratica_profissional,
                    data=datetime.datetime.now(),
                    tipo=tipo_notificacao,
                    notificador=None,
                    email_destinatario=vinculo_orientador.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()

    def notificar_pendencia_de_assinatura_supervisor(self):
        if self.pode_coletar_assinaturas_eletronicas() and not self.assinatura_supervisor and self.pratica_profissional.supervisor:
            vinculo_supervisor = self.pratica_profissional.supervisor
            tipo_notificacao = (
                NotificacaoPendencia.NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_SUPERVISOR
                if self.eh_relatorio_do_supervisor
                else NotificacaoPendencia.NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_ALUNO
            )
            # evita envios repetitivos num curto período
            if not NotificacaoPendencia.objects.filter(
                pratica_profissional=self.pratica_profissional,
                tipo=tipo_notificacao,
                email_destinatario=vinculo_supervisor.email_notificacao,
                data__gte=datetime.datetime.now() - timedelta(hours=1),
            ).exists():
                url_relatorios = (
                    f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}'
                    f'?tab={"avaliacaosupervisor" if self.eh_relatorio_do_supervisor else "relatorios"}'
                )
                if self.eh_relatorio_do_supervisor:
                    descricao_relatorio = 'seu Relatório de Atividades de Estágio'
                else:
                    descricao_relatorio = 'Relatório de Atividades de um estágio sob sua supervisão'

                titulo = '[SUAP] Notificação: Pendência de Assinatura em Relatório de Atividades de Estágio'
                mensagem = render_to_string(
                    template_name='notificacoes/estagio_pendencia_assinatura_relatorio.html',
                    context={
                        'nome_supervisor': vinculo_supervisor.nome,
                        'descricao_relatorio': descricao_relatorio,
                        'url_relatorios': url_relatorios,
                        'versao': 'supervisor',
                    },
                )
                send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [vinculo_supervisor])
                notificacao = NotificacaoPendencia(
                    pratica_profissional=self.pratica_profissional,
                    data=datetime.datetime.now(),
                    tipo=tipo_notificacao,
                    notificador=None,
                    email_destinatario=vinculo_supervisor.email_notificacao,
                    mensagem_enviada=f'{titulo}<br/>{mensagem}',
                )
                notificacao.save()


class RelatorioSemestralEstagioAtividade(models.ModelPlus):
    REALIZADA_SIM = 1
    REALIZADA_NAO = 2
    REALIZADA_CHOICES = [[REALIZADA_SIM, 'Realizada'], [REALIZADA_NAO, 'Não Realizada']]

    NAO_REALIZADA_MOTIVO_TEMPO_INSUFICIENTE = 1
    NAO_REALIZADA_MOTIVO_CONHECIMENTO_INSUFICIENTE = 2
    NAO_REALIZADA_MOTIVO_MUDANCA_PLANO_ATIVIDADES = 3
    NAO_REALIZADA_MOTIVO_SUBSTITUICAO_POR_OUTRA_ATIVIDADE = 4
    NAO_REALIZADA_MOTIVO_OUTRO_MOTIVO = 5
    NAO_REALIZADA_MOTIVO_CHOICES = [
        [NAO_REALIZADA_MOTIVO_TEMPO_INSUFICIENTE, 'Tempo insuficiente'],
        [NAO_REALIZADA_MOTIVO_CONHECIMENTO_INSUFICIENTE, 'Conhecimento insuficiente'],
        [NAO_REALIZADA_MOTIVO_MUDANCA_PLANO_ATIVIDADES, 'Mudança no plano de atividades'],
        [NAO_REALIZADA_MOTIVO_SUBSTITUICAO_POR_OUTRA_ATIVIDADE, 'Substituição por outra atividade'],
        [NAO_REALIZADA_MOTIVO_OUTRO_MOTIVO, 'Outro motivo'],
    ]

    relatorio_semestral = models.ForeignKeyPlus(RelatorioSemestralEstagio, editable=False)
    atividade = models.ForeignKeyPlus(Atividade, editable=False)
    realizada = models.IntegerField('Realização da Atividade', choices=REALIZADA_CHOICES, help_text='A atividade prevista no plano foi realizada?')
    nao_realizada_motivo = models.IntegerField('Motivo', choices=NAO_REALIZADA_MOTIVO_CHOICES, blank=True, null=True)
    nao_realizada_motivo_descricao = models.TextField('Descrição do motivo', blank=True, null=True)

    class Meta:
        verbose_name = 'Avaliação Semestral de Atividade de Estágio'
        verbose_name_plural = 'Avaliações Semestrais de Atividade de Estágio'

    @property
    def is_realizada(self):
        return self.realizada == RelatorioSemestralEstagioAtividade.REALIZADA_SIM

    def get_motivo_nao_realizada(self):
        if self.nao_realizada_motivo == RelatorioSemestralEstagioAtividade.NAO_REALIZADA_MOTIVO_OUTRO_MOTIVO:
            return f'Outro motivo: {self.nao_realizada_motivo_descricao}'
        else:
            return self.get_nao_realizada_motivo_display()

    def __str__(self):
        return f'Avaliação Semestral de Atividade de Estágio({self.pk})'


class OrientacaoEstagio(models.ModelPlus):
    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional')
    orientador = models.ForeignKeyPlus(Professor, verbose_name='Orientador')
    data = models.DateFieldPlus(verbose_name='Data da Reunião de Orientação')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    local = models.CharFieldPlus('Local')
    descricao = models.TextField('Descrição do Conteúdo da Orientação', blank=True, null=True)

    class Meta:
        ordering = ('-data',)

    def save(self, *args, **kwargs):
        titulo = '[SUAP] Orientação de Estágio Agendada'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_orientacao_cadastrada.html',
            context={
                'nome_orientador': self.pratica_profissional.orientador.get_nome(),
                'concedente': str(self.pratica_profissional.empresa),
                'data_reuniao': self.data,
                'horario_reuniao': self.hora_inicio,
                'local_reuniao': self.local,
                'url_estagio': f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}',
            },
        )

        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.pratica_profissional.aluno.get_vinculo()])
        email_aluno = self.pratica_profissional.get_email_aluno()
        if email_aluno:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self.pratica_profissional,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_ORIENTACAO_ESTAGIO,
                notificador=self.user,
                email_destinatario=email_aluno,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()
        super().save()


class NotificacaoPendencia(models.ModelPlus):
    NOTIFICACAO_VISITA_TRIMESTRAL = 1
    NOTIFICACAO_RELATORIO_SEMESTRAL_ALUNO = 2
    NOTIFICACAO_RELATORIO_SEMESTRAL_SUPERVISOR = 3
    NOTIFICACAO_INICIAL = 4
    NOTIFICACAO_APTO_PARA_CONCLUSAO = 5
    NOTIFICACAO_ORIENTACAO_ESTAGIO = 6
    NOTIFICACAO_MATRICULA_IRREGULAR = 7
    NOTIFICACAO_MATRICULA_REGULARIZADA = 8
    NOTIFICACAO_FINAL_MATRICULA_IRREGULAR = 9
    NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE = 10
    NOTIFICACAO_ASSINATURA_DECURSO_PRAZO_PENDENTE = 11
    NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_ALUNO = 12
    NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_SUPERVISOR = 13
    NOTIFICACAO_DIVERGENCIA_RELATORIO_ATIVIDADES = 14
    NOTIFICACAO_ASSINATURA_TERMO_REALIZACAO_ESTAGIO = 15

    TIPO_CHOICES = [
        [NOTIFICACAO_VISITA_TRIMESTRAL, 'Notificação de visita trimestral do orientador.'],
        [NOTIFICACAO_RELATORIO_SEMESTRAL_ALUNO, 'Notificação de relatório semestral do aluno.'],
        [NOTIFICACAO_RELATORIO_SEMESTRAL_SUPERVISOR, 'Notificação de relatório semestral do supervisor.'],
        [NOTIFICACAO_INICIAL, 'Notificação inicial'],
        [NOTIFICACAO_APTO_PARA_CONCLUSAO, 'Notificação de estágio apto para encerramento.'],
        [NOTIFICACAO_ORIENTACAO_ESTAGIO, 'Notificação de orientação de estágio.'],
        [NOTIFICACAO_MATRICULA_IRREGULAR, 'Notificação de matrícula irregular.'],
        [NOTIFICACAO_MATRICULA_REGULARIZADA, 'Notificação de matrícula regularizada.'],
        [NOTIFICACAO_FINAL_MATRICULA_IRREGULAR, 'Notificação de final de matrícula irregular.'],
        [NOTIFICACAO_NECESSIDADE_ATUALIZACAO_PAE, 'Notificação de necessidade de atualização do Plano de Atividades do Estágio.'],
        [NOTIFICACAO_ASSINATURA_DECURSO_PRAZO_PENDENTE, 'Notificação de necessidade de assinatura da justificativa de Decurso de Prazo.'],
        [NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_ALUNO, 'Notificação de necessidade de assinatura do relatório semestral do estagiário.'],
        [NOTIFICACAO_ASSINATURA_RELATORIO_SEMESTRAL_SUPERVISOR, 'Notificação de necessidade de assinatura do relatório semestral do supervisor.'],
        [NOTIFICACAO_DIVERGENCIA_RELATORIO_ATIVIDADES, 'Notificação de divergências em Relatórios de Atividades.'],
        [NOTIFICACAO_ASSINATURA_TERMO_REALIZACAO_ESTAGIO, 'Notificação de necessidade de assinatura de Termo de Realização de Estágio.'],
    ]

    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional')
    notificador = models.ForeignKeyPlus('comum.User', verbose_name='Notificador', null=True)
    data = models.DateTimeFieldPlus('Data da Notificação')
    tipo = models.IntegerField('Tipo', choices=TIPO_CHOICES)
    email_destinatario = models.TextField('E-mail')
    mensagem_enviada = models.TextField('Mensagem Enviada')

    class Meta:
        ordering = ('-data',)
        verbose_name = 'Notificação de Pendência'
        verbose_name_plural = 'Notificações de Pendências'

    def __str__(self):
        return f'{self.pk}-{self.get_tipo_display()}'


class TrimestreNaoVisitadoNotificado(models.ModelPlus):
    inicio = models.DateTimeFieldPlus('Início')
    fim = models.DateTimeFieldPlus('Fim')
    notificacao = models.ForeignKeyPlus(NotificacaoPendencia, verbose_name='Notificação de Pendência')


class RelatorioSemestralPendenteNotificado(models.ModelPlus):
    inicio = models.DateTimeFieldPlus('Início')
    fim = models.DateTimeFieldPlus('Fim')
    eh_relatorio_do_supervisor = models.BooleanField(editable=False, default=True)
    notificacao = models.ForeignKeyPlus(NotificacaoPendencia, verbose_name='Notificação de Pendência')


class JustificativaVisitaEstagio(models.ModelPlus):
    pratica_profissional = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Estágio')
    inicio = models.DateFieldPlus('Início')
    fim = models.DateFieldPlus('Fim')
    motivos = models.TextField('Informo que a visita à organização concedente não foi realizada pelos seguintes motivos', blank=False)
    outros_acompanhamentos = models.TextField(
        'Foram realizadas outras formas de acompanhamento do (a) aluno (a) sob sua orientação? Se sim, informe quais', blank=True
    )
    formulario_justificativa = models.FileFieldPlus(
        'Formulário de Justificativa',
        help_text='Esse documento deve ser solicitado ao Coordenador de Estágios, preenchido pelo orientador, e assinado pelo (a) Aluno (a) e Coordenador de Curso/Diretor Acadêmico. Limite de tamanho do arquivo 2MB.',
        blank=False,
        upload_to='justificativa_visita_estagimo/relatorio',
        max_file_size=2097152,
    )
    relatorio_interno = models.FileFieldPlus(
        'Relatório de Justificativa Visita',
        help_text='Relatório gerado pelo sistema após o preenchimento deste formulário.',
        blank=True,
        null=True,
        upload_to='justificativa_visita_estagio/relatorio_interno',
        max_file_size=2097152,
    )
    assinatura_orientador = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Orientador',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_orientador',
    )
    assinatura_estagiario = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Estagiário',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_estagiario',
    )
    # Campo descontinuado. Mantido apenas para preservar assinaturas antigas.
    assinatura_coordenador_curso = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Coordenador de Curso',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_coordenador_curso',
    )
    assinatura_coordenador_extensao = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Coordenador de Extensão',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_coordenador_extensao',
    )
    assinatura_diretor_academico = models.ForeignKeyPlus(
        'AssinaturaEletronica',
        verbose_name='Assinatura Eletrônica do Diretor Acadêmico',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='justificativa_diretor_academico',
    )

    def save(self):
        if not self.pk:
            self.notificar_pendencia_assinatura()
        super().save()

    def pode_assinar(self, user=None):
        user = user or tl.get_user()
        if self.assinatura_orientador is None:
            # Verifica se é orientador.
            # O fluxo termina aqui se não for, pois a assinatura do orientador é pré-requisito para as demais.
            return self.pratica_profissional.eh_orientador(user)
        if self.assinatura_coordenador_extensao is None and self.pratica_profissional.eh_coordenador_de_extensao(user):
            return True
        if self.assinatura_diretor_academico is None and self.pratica_profissional.eh_diretor_academico(user):
            return True
        return self.assinatura_estagiario is None and self.pratica_profissional.eh_estagiario(user)

    def assinar(self, user, papel):
        if papel == 'Orientador' and self.assinatura_orientador is None and self.pratica_profissional.eh_orientador(user):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_orientador = assinatura
        if (
            papel == 'Coordenador de Extensão'
            and self.assinatura_coordenador_extensao is None
            and self.pratica_profissional.eh_coordenador_de_extensao(user)
        ):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_coordenador_extensao = assinatura
        if papel == 'Diretor Acadêmico' and self.assinatura_diretor_academico is None and self.pratica_profissional.eh_diretor_academico(user):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_diretor_academico = assinatura
        if papel == 'Aluno' and self.assinatura_estagiario is None and self.pratica_profissional.eh_estagiario(user):
            assinatura = AssinaturaEletronica(vinculo=user.get_vinculo())
            assinatura.assinar()
            self.assinatura_estagiario = assinatura
        self.save()

    def notificar_pendencia_assinatura(self):
        titulo = '[SUAP] Pendência de Assinatura da Justificativa de Decurso de Prazo de Orientação de Estágio'
        mensagem = render_to_string(
            template_name='notificacoes/estagio_pendencia_assinatura_justificativa_visita.html',
            context={
                'nome_aluno': normalizar_nome_proprio(self.pratica_profissional.aluno.get_nome_social_composto()),
                'matricula_aluno': self.pratica_profissional.aluno.matricula,
                'url_estagio': f'{settings.SITE_URL}{self.pratica_profissional.get_absolute_url()}',
            },
        )

        coordenadores_extensao = get_coordenadores_extensao(self.pratica_profissional.aluno)
        vinculos = [
            self.pratica_profissional.aluno.get_vinculo(),
            self.pratica_profissional.orientador.vinculo,
            *get_coordenadores_vinculos(coordenadores_extensao),
        ]
        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)
        for vinculo in vinculos:
            notificacao = NotificacaoPendencia(
                pratica_profissional=self.pratica_profissional,
                data=datetime.datetime.now(),
                tipo=NotificacaoPendencia.NOTIFICACAO_ASSINATURA_DECURSO_PRAZO_PENDENTE,
                notificador=None,
                email_destinatario=vinculo.user.email,
                mensagem_enviada=f'{titulo}<br/>{mensagem}',
            )
            notificacao.save()

    def is_coordenador_curso(self, user):
        curso = self.pratica_profissional.aluno.curso_campus
        return (curso.coordenador and curso.coordenador.user == user) or (curso.coordenador_2 and curso.coordenador_2.user == user)

    def get_assinaturas_pendentes(self, user):
        result = []
        if self.assinatura_orientador is None and self.pratica_profissional.eh_orientador(user):
            result.append('Orientador')
        if self.assinatura_orientador:
            if self.assinatura_estagiario is None and self.pratica_profissional.eh_estagiario(user):
                result.append('Aluno')
            if self.assinatura_coordenador_extensao is None and self.assinatura_diretor_academico is None:
                if self.pratica_profissional.eh_coordenador_de_extensao(user):
                    result.append('Coordenador de Extensão')
                if self.pratica_profissional.eh_diretor_academico(user):
                    result.append('Diretor Acadêmico')
        return result


class SolicitacaoCancelamentoEncerramentoEstagio(models.ModelPlus):
    AGUARDANDO_RESPOSTA = 1
    DEFERIDA = 2
    INDEFERIDA = 3
    SITUACAO_CHOICES = [[AGUARDANDO_RESPOSTA, 'Aguardando Resposta'], [DEFERIDA, 'Deferida'], [INDEFERIDA, 'Indeferida']]

    estagio = models.ForeignKeyPlus(PraticaProfissional, verbose_name='Prática Profissional', null=True)
    atividade_profissional_efetiva = models.ForeignKeyPlus(AtividadeProfissionalEfetiva, verbose_name='Atividade Profissional Efetiva', null=True)
    user = models.ForeignKeyPlus('comum.User', verbose_name='Solicitante')
    data = models.DateTimeFieldPlus('Data da Solicitação')
    justificativa = models.TextField('Justificativa')
    situacao = models.IntegerField('Situação', choices=SITUACAO_CHOICES, default=AGUARDANDO_RESPOSTA)
    aprendizagem = models.ForeignKeyPlus(Aprendizagem, verbose_name='Aprendizagem', null=True)

    class Meta:
        ordering = ('-data',)
        verbose_name = 'Solicitação de Cancelamento do Encerramento'
        verbose_name_plural = 'Solicitações de Cancelamento do Encerramento'

    def __str__(self):
        return f'Solicitação de Cancelamento de Encerramento de {self.get_tipo()} ({self.pk})'

    def save(self):
        if not self.pk:
            self.data = datetime.datetime.now()
        super().save()

    def get_tipo(self):
        if self.estagio:
            return 'Estágio'
        elif self.atividade_profissional_efetiva:
            return 'Atividade Profissional Efetiva'
        elif self.aprendizagem:
            return 'Aprendizagem'
        else:
            return 'Tipo desconhecido'

    @property
    def campus_do_estagio_ou_afim(self):
        aluno = None
        if self.estagio:
            aluno = self.estagio.aluno
        elif self.aprendizagem:
            aluno = self.aprendizagem.aprendiz
        elif self.atividade_profissional_efetiva:
            aluno = self.atividade_profissional_efetiva.aluno

        return aluno.campus if aluno else None


class AssinaturaEletronica(models.ModelPlus):
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vinculo', null=True, blank=True, related_name='assinaturas_estagio')
    data = models.DateTimeFieldPlus(verbose_name='Data da Assinatura', null=True)
    chave = models.CharFieldPlus(verbose_name='Chave', null=True)

    class Meta:
        verbose_name = 'Assinatura Eletrônica'
        verbose_name_plural = 'Assinaturas Eletrônicas'

    def __str__(self):
        return f'Assinatura de {self.vinculo}'

    def assinar(self):
        self.data = datetime.datetime.now()
        self.chave = uuid.uuid1().hex
        self.save()
