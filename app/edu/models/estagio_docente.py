import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.aggregates import Sum

from comum.models import Configuracao
from djtools.db import models
from djtools.templatetags.filters import format_
from djtools.utils import send_notification
from edu.managers import EstagioDocenteManager
from edu.models.cadastros_gerais import Escola
from edu.models.logs import LogModel


class EstagioDocente(LogModel):
    # Dados gerais
    objects = models.Manager()
    locals = EstagioDocenteManager()

    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', null=True, on_delete=models.CASCADE)
    convenio = models.ForeignKeyPlus('convenios.Convenio', verbose_name='Convênio', null=True, blank=True)
    escola = models.CharFieldPlus('Escola', null=True, blank=False)
    local = models.ForeignKeyPlus(Escola, verbose_name='Escola', null=True, blank=False)
    # Status
    NIVEL_FUNDAMENTAL = 1
    NIVEL_MEDIO = 2
    NIVEL_FUNDAMENTAL_E_MEDIO = 3
    NIVEL_CHOICES = [[NIVEL_FUNDAMENTAL, 'Fundamental'], [NIVEL_MEDIO, 'Médio'], [NIVEL_FUNDAMENTAL_E_MEDIO, 'Fundamental e Médio']]
    nivel = models.IntegerField('Nível de Ensino', null=True, blank=False, choices=NIVEL_CHOICES)
    matricula_diario = models.ForeignKeyPlus(
        'edu.MatriculaDiario', verbose_name='Matrícula Diário', null=False, blank=False, on_delete=models.CASCADE
    )
    professor_coordenador = models.ForeignKeyPlus(
        'edu.Professor', verbose_name='Professor Coordenador', related_name='estagiodocente_coordenador_set', null=True
    )
    professor_orientador = models.ForeignKeyPlus(
        'edu.Professor', verbose_name='Professor Orientador', related_name='estagiodocente_orientador_set', null=True
    )

    # Período
    data_inicio = models.DateFieldPlus('Data de Início', null=True, blank=False)
    data_fim = models.DateFieldPlus('Data de Encerramento', null=True, blank=False)
    data_final_envio_portfolio = models.DateFieldPlus('Data de Final para Envio do Portfólio', null=True, blank=False)

    # Documentação
    plano_estagio = models.FileFieldPlus(
        'Plano de Atividades',
        null=True,
        blank=True,
        max_length=255,
        upload_to='edu/planos_de_estagio',
        help_text='Plano de atividades do Estágio Docente ou do Programa Residência Pedagógica',
    )
    termo_compromisso = models.FileFieldPlus(
        'Termo de Compromisso',
        null=True,
        blank=True,
        max_length=255,
        upload_to='edu/termos_compromissos',
        help_text='Termo de Compromisso do Estágio Docente ou do Programa Residência Pedagógica',
    )
    documentacao_comprobatoria = models.FileFieldPlus(
        'Documentação Comprobatória de Prática Efetiva',
        null=True,
        blank=True,
        max_length=255,
        upload_to='edu/documentacao_comprobatoria_pratica_anterior',
        help_text='Comprovantes de prática anterior substituem o Plano de Atividades e o Termo de Compromisso.',
    )

    # Seguro
    nome_seguradora = models.CharFieldPlus('Nome da Seguradora', null=True, blank=False)
    numero_seguro = models.CharFieldPlus('Número da Apólice do Seguro', null=True, blank=False)

    # Professor Colaborador
    nome_professor_colaborador = models.CharFieldPlus('Nome', null=True, blank=False)
    cpf_professor_colaborador = models.CharFieldPlus('CPF', null=True, blank=False)
    telefone_professor_colaborador = models.CharFieldPlus('Telefone', null=True, blank=True)
    cargo_professor_colaborador = models.CharFieldPlus('Cargo', null=True, blank=False)
    formacao_professor_colaborador = models.CharFieldPlus('Formação', null=True, blank=True)
    email_professor_colaborador = models.CharFieldPlus('E-mail', null=True, blank=True)

    # Observações
    observacoes = models.TextField('Observações', null=True, blank=True)

    # Encerramento
    portfolio = models.FileFieldPlus('Portfólio', null=True, blank=True, max_length=255, upload_to='edu/portfolio')
    avaliacao_do_professor_colaborador = models.FileFieldPlus(
        'Avaliação do Professor Colaborador', null=True, blank=True, max_length=255, upload_to='edu/avaliacao_do_professor_colaborador'
    )
    avaliacao_do_orientador = models.FileFieldPlus(
        'Avaliação do Orientador', null=True, blank=True, max_length=255, upload_to='edu/avaliacao_do_orientador'
    )
    ch_final = models.IntegerField('C.H. Final', null=True, blank=True)
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    # Status
    SITUACAO_AGUARDANDO_INFORMACOES_CADASTRAIS = 1
    SITUACAO_EM_ANDAMENTO = 2
    SITUACAO_AGUARDANDO_ENCERRAMENTO = 3
    SITUACAO_ENCERRADO = 4
    SITUACAO_MUDANCA = 5
    SITUACAO_NAO_CONCLUIDO = 6
    SITUACAO_CHOICES = [
        [SITUACAO_AGUARDANDO_INFORMACOES_CADASTRAIS, 'Aguardando Informações Cadastrais'],
        [SITUACAO_EM_ANDAMENTO, 'Em Andamento'],
        [SITUACAO_AGUARDANDO_ENCERRAMENTO, 'Aguardando Encerramento'],
        [SITUACAO_ENCERRADO, 'Encerrado por Conclusão'],
        [SITUACAO_MUDANCA, 'Mudança de Escola'],
        [SITUACAO_NAO_CONCLUIDO, 'Não Concluído'],
    ]
    situacao = models.IntegerField('Situação', default=SITUACAO_AGUARDANDO_INFORMACOES_CADASTRAIS, null=True, blank=True, choices=SITUACAO_CHOICES)

    class Meta:
        verbose_name = 'Estágio Docente'
        verbose_name_plural = 'Estágios Docentes'

    def __str__(self):
        return f'({self.pk}) Estágio de {self.matricula_diario.matricula_periodo.aluno.get_nome_social_composto()} ({self.matricula_diario.matricula_periodo.aluno.matricula}), no período {self.matricula_diario.matricula_periodo.ano_letivo.ano}.{self.matricula_diario.matricula_periodo.periodo_letivo}'

    def get_absolute_url(self):
        return f'/edu/estagio_docente/{self.pk}/'

    def nome_aluno(self):
        return (
            f'{self.matricula_diario.matricula_periodo.aluno.get_nome_social_composto()} ({self.matricula_diario.matricula_periodo.aluno.matricula})'
        )

    nome_aluno.admin_order_field = 'matricula_diario__matricula_periodo__aluno__pessoa_fisica__nome'
    nome_aluno.short_description = 'Aluno'

    def get_escola(self):
        nome_escola = self.local.nome if self.local_id else self.escola
        return f'{format_(nome_escola)} ({format_(self.get_nivel_display())})' if nome_escola else None

    get_escola.admin_order_field = 'escola'
    get_escola.short_description = 'Escola'

    def is_ultimo_a_ser_finalizado(self):
        return not self.matricula_diario.estagiodocente_set.all().exclude(pk=self.pk).exclude(ch_final__isnull=False).exists()

    def clean(self, *args, **kwargs):
        if self.ch_final and not self.justificativa and self.is_ultimo_a_ser_finalizado():
            ch_total = self.ch_final + (
                self.matricula_diario.estagiodocente_set.all().exclude(pk=self.pk).aggregate(Sum('ch_final'))['ch_final__sum'] or 0
            )
            carga_horaria_total_componente = (
                self.matricula_diario.diario.componente_curricular.componente_curricular_associado
                and self.matricula_diario.diario.componente_curricular.componente_curricular_associado.get_carga_horaria_total()
                or self.matricula_diario.diario.componente_curricular.get_carga_horaria_total()
            )
            if ch_total != carga_horaria_total_componente:
                estagios = self.matricula_diario.estagiodocente_set.all().exclude(pk=self.pk)
                if estagios.exists():
                    cargas_horarias = '<ul>'
                    for estagio in estagios:
                        cargas_horarias = cargas_horarias + f'<li>{estagio.get_escola()} ({estagio.ch_final} horas)</li>'
                    cargas_horarias = cargas_horarias + '</ul>'
                    raise ValidationError(
                        f'A soma de cargas horárias deve ser igual a {carga_horaria_total_componente}.<br/>Escolas onde o aluno estagiou neste estágio docente: {cargas_horarias}'
                    )
                raise ValidationError({'ch_final': f'A carga horária deve ser igual a {carga_horaria_total_componente}.'})

    def notificar(self):
        diferenca = datetime.date.today() - self.data_inicio
        soma = 0
        if diferenca.days > 60:
            url_servidor = Configuracao.get_valor_por_chave('protocolo', 'url_consulta_publica')
            titulo = 'Notificação de Pendência (Estágio Docente)'
            assunto = f'Prezado orientador, você ainda não registrou a visita referente ao estágio docente de {self.matricula_diario.matricula_periodo.aluno}. Para fazê-lo, acesse o endereço a seguir: {url_servidor}accounts/login/?next=/edu/cadastrar_visita_estagio_docente/{self.pk}/.'
            send_notification(titulo, assunto, settings.DEFAULT_FROM_EMAIL, [self.professor_orientador.vinculo], fail_silently=True)
            soma += 1
        diferenca = self.data_final_envio_portfolio - datetime.date.today()
        if diferenca.days <= 15:
            url_servidor = Configuracao.get_valor_por_chave('protocolo', 'url_consulta_publica')
            titulo = 'Notificação de Pendência (Estágio Docente)'
            assunto = f'Prezado {self.matricula_diario.matricula_periodo.aluno}, informamos que o prazo para entrega do portfólio referente ao estágio docente {self} se encerra dia {format_(self.data_final_envio_portfolio)}. Para fazê-lo, acesse o endereço a seguir: {url_servidor}accounts/login/?next=/edu/aluno/{self.pk}/?tab=estagios_docentes'
            send_notification(
                titulo, assunto, settings.DEFAULT_FROM_EMAIL, [self.matricula_diario.matricula_periodo.aluno.get_vinculo()], fail_silently=True
            )
            soma += 1
        return soma

    def tipo_estagio_docente(self):
        return self.matricula_diario.diario.componente_curricular.get_tipo_estagio_docente_display()

    tipo_estagio_docente.admin_order_field = 'matricula_diario__diario__componente_curricular__tipo_estagio_docente'
    tipo_estagio_docente.short_description = 'Tipo'

    def encerrar_sem_conclusao(self):
        self.situacao = self.SITUACAO_NAO_CONCLUIDO
        super().save()

    def save(self, *args, **kwargs):
        if self.situacao == self.SITUACAO_AGUARDANDO_INFORMACOES_CADASTRAIS and self.professor_orientador:
            url_servidor = Configuracao.get_valor_por_chave('protocolo', 'url_consulta_publica')
            titulo = '[SUAP] Seleção para Orientação de Estágio Docente'
            assunto = (
                '<h1>Ensino</h1>'
                '<h2>Seleção para Orientação de Estágio Docente</h2>'
                f'<p>Prezado orientador, você foi cadastrado para orientação do aluno {self.matricula_diario.matricula_periodo.aluno} em estágio docente.</p>'
                f'<p>Você pode acessar os dados do estágio no endereço a seguir: {url_servidor}accounts/login/?next=/edu/estagio_docente/{self.pk}/.</p>'
            )
            self.professor_orientador.vinculo.user.email_user(titulo, assunto, fail_silently=True)
            titulo = '[SUAP] Cadastro de Estágio Docente'
            assunto = (
                '<h1>Ensino</h1>'
                '<h2>Cadastro de Estágio Docente</h2>'
                f'<p>Caro {self.matricula_diario.matricula_periodo.aluno},</p>'
                f'<p>Informamos que você foi cadastrado no estágio docente {self}.</p>'
                f'<p>A data limite para entrega do portfólio deste estágio é {format_(self.data_final_envio_portfolio)}.</p>'
                f'<p>Para observar o seu cadastro, acesse:\n {url_servidor}accounts/login/?next=/edu/aluno/{self.matricula_diario.matricula_periodo.aluno.matricula}/?tab=estagios_docentes.</p>'
            )
            aluno = self.matricula_diario.matricula_periodo.aluno
            send_notification(titulo, assunto, settings.DEFAULT_FROM_EMAIL, [aluno.get_vinculo()], fail_silently=True)

        if self.situacao == self.SITUACAO_MUDANCA:
            estagio_no_banco = EstagioDocente.objects.filter(pk=self.pk)[0]
            if estagio_no_banco.situacao != self.SITUACAO_MUDANCA:
                EstagioDocente.objects.create(matricula_diario=self.matricula_diario)
            return super().save(*args, **kwargs)
        if self.get_escola() and self.data_fim >= datetime.date.today() and not self.avaliacao_do_professor_colaborador:
            self.situacao = self.SITUACAO_EM_ANDAMENTO
            self.notificar()
        elif self.get_escola() and self.data_fim < datetime.date.today() and not self.ch_final:
            self.situacao = self.SITUACAO_AGUARDANDO_ENCERRAMENTO
            self.notificar()
        elif (
            self.get_escola()
            and self.avaliacao_do_professor_colaborador
            and self.avaliacao_do_orientador
            and self.ch_final
            and self.visitaestagiodocente_set.exists()
        ):
            self.situacao = self.SITUACAO_ENCERRADO

        return super().save(*args, **kwargs)

    def get_estagios_concomitantes(self):
        estagios = self.matricula_diario.estagiodocente_set.exclude(pk=self.pk).exclude(situacao=self.SITUACAO_MUDANCA)
        return estagios

    def get_periodo_duracao(self):
        if self.data_fim:
            return [self.data_inicio, self.data_fim]
        else:
            return [None, None]

    def is_encerrado(self):
        return self.situacao in [self.SITUACAO_ENCERRADO, self.SITUACAO_NAO_CONCLUIDO]


class VisitaEstagioDocente(models.ModelPlus):
    estagio_docente = models.ForeignKeyPlus('edu.EstagioDocente', verbose_name='Estágio Docente')
    # Visita do orientador
    data_visita = models.DateFieldPlus('Data da Visita', null=False, blank=False)
    relatorio = models.FileFieldPlus('Relatório de Visita', null=True, blank=True, max_length=255, upload_to='edu/relatorio_visita')
    desenvolvendo_atividades_previstas = models.BooleanField('O aluno está desenvolvendo as atividades previstas?', null=False, blank=False)
    informacoes_complementares = models.TextField(
        'Informações Complementares', help_text='Informações consideradas relevantes, mas que não foram contempladas no itens anteriores.', blank=True
    )

    class Meta:
        verbose_name = 'Visita do Orientador'
        verbose_name_plural = 'Visitas do Orientador'

    def __str__(self):
        return f'Visita realizada em {self.data_visita}'

    def clean(self):
        if (
            self.data_visita
            and self.estagio_docente.data_fim
            and self.estagio_docente.data_inicio
            and (self.data_visita > self.estagio_docente.data_fim or self.data_visita < self.estagio_docente.data_inicio)
        ):
            raise ValidationError(
                {
                    'data_visita': f'A data da visita deve estar compreendida entre a data de início ({format_(self.estagio_docente.data_inicio)}) e a data de fim ({format_(self.estagio_docente.data_fim)}).'
                }
            )
        if not self.desenvolvendo_atividades_previstas and not self.informacoes_complementares:
            raise ValidationError(
                {
                    'informacoes_complementares': 'Caso a resposta à pergunta "O aluno está desenvolvendo atividades as atividades previstas?" seja não, Informações Complementares são obrigatórias.'
                }
            )
