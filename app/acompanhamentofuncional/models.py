from datetime import date, timedelta

from django.conf import settings
from django.utils.safestring import mark_safe

from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.templatetags.filters import in_group
from djtools.utils import send_notification
from rh.models import Servidor


class ServidorCessao(ModelPlus):
    STATUS_PROCESSO_ATIVO = 1
    STATUS_PROCESSO_FINALIZADO = 2
    STATUS_PROCESSO_CHOICES = [[STATUS_PROCESSO_ATIVO, 'Ativo'], [STATUS_PROCESSO_FINALIZADO, 'Finalizado']]

    STATUS_PRAZO_NO_PRAZO = 1
    STATUS_PRAZO_ESGOTANDO = 2
    STATUS_PRAZO_ESGOTADO = 3
    STATUS_PRAZO_CHOICES = [[STATUS_PRAZO_NO_PRAZO, 'No prazo'], [STATUS_PRAZO_ESGOTANDO, 'Esgotando'], [STATUS_PRAZO_ESGOTADO, 'Esgotado']]

    NUM_DIAS_RESTANTES_NOTIFICACAO_1 = 60
    NUM_DIAS_RESTANTES_NOTIFICACAO_2 = 30

    TIPO_EXERCICIO_CESSAO = 1
    TIPO_EXERCICIO_REQUISICAO = 2
    TIPO_EXERCICIO_PROVISORIO = 3
    TIPO_EXERCICIO_COOPERACAO = 4
    TIPO_EXERCICIO_CHOICES = [
        [TIPO_EXERCICIO_CESSAO, 'Cessão'],
        [TIPO_EXERCICIO_REQUISICAO, 'Requisição'],
        [TIPO_EXERCICIO_PROVISORIO, 'Exercício Provisório'],
        [TIPO_EXERCICIO_COOPERACAO, 'Cooperação Técnica'],
    ]

    servidor_cedido = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor Cedido', on_delete=models.CASCADE)
    tipo_exercicio = models.IntegerField('Tipo de Exercício', choices=TIPO_EXERCICIO_CHOICES, default=TIPO_EXERCICIO_CESSAO)
    numero_portaria = models.IntegerField('Número da Portaria', null=True, blank=True)
    instituicao_destino = models.ForeignKeyPlus(
        'rh.Instituicao', blank=True, null=True, verbose_name='Instituição/Órgão Destino', on_delete=models.CASCADE
    )
    ressarcimento_mensal = models.BooleanField(
        'Com Ressarcimento',
        default=False,
        help_text='Ressarcimento mensal da remuneração do servidor por parte do órgão cessionário',
        choices=[[True, 'Sim'], [False, 'Não']],
    )
    data_limite_retorno = models.DateField(
        'Data Limite', help_text='Data na qual o servidor deverá retornar (deixe em branco para retorno indeterminado)', blank=True, null=True
    )
    observacao = models.TextField('Observações', null=True, blank=True)
    status_prazo = models.IntegerField('Situação do Prazo', choices=STATUS_PRAZO_CHOICES, default=STATUS_PRAZO_NO_PRAZO)
    status_processo = models.IntegerField('Situação do Processo', choices=STATUS_PROCESSO_CHOICES, default=STATUS_PROCESSO_ATIVO)
    tipo_afastamento = models.ForeignKeyPlus(
        'ponto.TipoAfastamento',
        verbose_name='Tipo de Afastamento',
        null=True,
        blank=True,
        help_text='Ponto SUAP: Tipo de Afastamento a partir do qual será criado um Afastamento a cada Frequência enviada.',
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = 'Exercício Externo'
        verbose_name_plural = 'Exercícios Externos'
        permissions = (('pode_adicionar_frequencia', 'Pode Adicionar Frequência'),)
        ordering = ('data_limite_retorno',)
        unique_together = ('numero_portaria',)

    def __str__(self):
        data_limite = self.data_limite_retorno
        if data_limite:
            data_limite = self.data_limite_retorno.strftime('%d/%m/%Y')
        else:
            data_limite = '-'
        return f'Servidor: {self.servidor_cedido} | Portaria: {self.numero_portaria} | Data Retorno: {data_limite} | Status: {self.get_status_processo_display()} | Prazo: {self.get_status_prazo_display()}'

    @property
    def chefe_imediato(self):
        # servidor chefe imediato do servidor cedido
        return self.servidor_cedido.chefes_imediatos()

    @property
    def dias_restantes(self):
        dias = None
        if self.data_limite_retorno:
            dias = (self.data_limite_retorno - date.today()).days
            if dias < 0:
                dias = 0
        return dias

    @property
    def status_processo_as_html(self):
        if self.status_processo == ServidorCessao.STATUS_PROCESSO_ATIVO:
            status_class = 'status-success'
        else:
            status_class = 'status-info'
        return mark_safe(f'<span class="status {status_class}">{self.get_status_processo_display()}</span>')

    @property
    def status_prazo_as_html(self):
        if self.status_processo == ServidorCessao.STATUS_PROCESSO_FINALIZADO:
            return mark_safe('<span>-</span>')
        else:
            if self.status_prazo == ServidorCessao.STATUS_PRAZO_NO_PRAZO:
                status_class = 'status-success'
            elif self.status_prazo == ServidorCessao.STATUS_PRAZO_ESGOTANDO:
                status_class = 'status-alert'
            else:
                status_class = 'status-error'
            return mark_safe(f'<span class="status {status_class}">{self.get_status_prazo_display()}</span>')

    @property
    def dias_restantes_as_html(self):
        if self.status_processo == ServidorCessao.STATUS_PROCESSO_FINALIZADO:
            return mark_safe('<span>-</span>')
        else:
            dias_restantes = self.dias_restantes
            if dias_restantes is not None:  # teste necessário, pois 0 e None têm significados diferentes nesse contexto
                if dias_restantes > ServidorCessao.NUM_DIAS_RESTANTES_NOTIFICACAO_1:
                    status_class = 'status-alert'
                else:
                    status_class = 'status-error'
            else:
                dias_restantes = 'Indeterminado'
                status_class = 'status-info'
            return mark_safe(f'<span class="status {status_class}">{dias_restantes}</span>')

    @classmethod
    def atualiza_prazos(cls, processos=None, save=True):
        if processos is None:
            processos = []
        if not processos:
            # procura processos ativos com prazo mudando para esgotando/esgotado e notifica via email se for o caso
            processos = ServidorCessao.objects.filter(status_processo=ServidorCessao.STATUS_PROCESSO_ATIVO)
        for processo in processos:
            dias = processo.dias_restantes
            if dias is not None:  # teste necessário, pois 0 e None têm significados diferentes nesse contexto
                prazo_esgotado = dias == 0
                prazo_esgotando_prazo_1 = not prazo_esgotado and dias <= ServidorCessao.NUM_DIAS_RESTANTES_NOTIFICACAO_1
                prazo_esgotando_prazo_2 = not prazo_esgotado and dias <= ServidorCessao.NUM_DIAS_RESTANTES_NOTIFICACAO_2

                if prazo_esgotado:
                    if processo.status_prazo != ServidorCessao.STATUS_PRAZO_ESGOTADO:
                        processo.status_prazo = ServidorCessao.STATUS_PRAZO_ESGOTADO
                elif prazo_esgotando_prazo_1 or prazo_esgotando_prazo_2:
                    if processo.status_prazo != ServidorCessao.STATUS_PRAZO_ESGOTANDO:
                        processo.status_prazo = ServidorCessao.STATUS_PRAZO_ESGOTANDO
                else:
                    processo.status_prazo = ServidorCessao.STATUS_PRAZO_NO_PRAZO
            else:
                processo.status_prazo = ServidorCessao.STATUS_PRAZO_NO_PRAZO

            if save:
                processo.save()
                if processo.status_prazo != ServidorCessao.STATUS_PRAZO_NO_PRAZO:
                    processo.notifica_via_email(dias)  # notifica apenas se o status do prazo mudar

    def notifica_via_email(self, dias_restantes):
        # notifica o servidor cedido e o seu chefe imediato (prazo esgotando (faltam X dias) ou prazo esgotado)
        destinatarios = []
        servidor_cedido = self.servidor_cedido
        destinatarios.append(servidor_cedido.get_vinculo())
        for chefe_imediato in self.chefe_imediato:
            destinatarios.append(chefe_imediato.get_vinculo())
        assunto = f'[SUAP] Acompanhamento Funcional: {self.get_tipo_exercicio_display()} do Servidor {self.servidor_cedido}'
        if dias_restantes == 0:
            mensagem = """<h1>{tipo_exercicio} do Servidor {servidor}</h1>
            <p>O processo referente a(o) {tipo_exercicio} do servidor {servidor} está com o prazo <strong>ESGOTADO</strong>.</p>""".format(
                tipo_exercicio=self.get_tipo_exercicio_display(), servidor=self.servidor_cedido
            )
        else:
            mensagem = """<h1>{tipo_exercicio} do Servidor {servidor}</h1>
            <p>O processo referente a(o) {tipo_exercicio} do servidor {servidor} está com o prazo
            esgotando ({dias} dias restantes).</p>""".format(
                tipo_exercicio=self.get_tipo_exercicio_display(), servidor=self.servidor_cedido, dias=dias_restantes
            )

        send_notification(
            assunto, mensagem, settings.DEFAULT_FROM_EMAIL, destinatarios, categoria=f'Acompanhamento Funcional: {self.get_tipo_exercicio_display()}'
        )

    @classmethod
    def is_servidor_rh_campus(cls, usuario):
        # servidor do grupo rh campus
        return in_group(usuario, 'Coordenador de Gestão de Pessoas')

    @classmethod
    def is_servidor_rh_sistemico(cls, usuario):
        # servidor do grupo rh sistêmico
        return in_group(usuario, 'Coordenador de Gestão de Pessoas Sistêmico')

    def save(self, *args, **kwargs):
        # atualiza os prazos do processo
        ServidorCessao.atualiza_prazos(processos=[self], save=False)
        # salva
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/acompanhamentofuncional/exibir_processo_cessao/{self.id:d}/'


class ServidorCessaoFrequencia(ModelPlus):
    servidor_cessao = models.ForeignKeyPlus('acompanhamentofuncional.ServidorCessao', editable=False, on_delete=models.CASCADE)
    data_inicial = models.DateFieldPlus('Data Inicial')
    data_final = models.DateFieldPlus('Data Final')
    arquivo = models.FileFieldPlus(upload_to='acompanhamentofuncional/servidorcessaofrequencia/', max_length=250)
    enviado_por = models.ForeignKeyPlus('comum.User', editable=False, on_delete=models.CASCADE)
    data_envio = models.DateFieldPlus('Data do Envio', editable=False)
    afastamento = models.ForeignKeyPlus('ponto.Afastamento', editable=False, null=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Frequência de Exercício Externo'
        verbose_name_plural = 'Frequências de Exercícios Externos'
        ordering = ('-data_inicial',)

    def __str__(self):
        return '{} - {}'.format(self.data_inicial.strftime('%d/%m/%Y'), self.data_final.strftime('%d/%m/%Y'))

    @property
    def quem_enviou(self):
        return self.enviado_por.get_relacionamento()

    def criar_afastamento(self):
        if self.servidor_cessao.tipo_afastamento:
            self.excluir_afastamento()
            #
            from ponto.models import Afastamento

            afastamento = Afastamento()
            afastamento.vinculo = self.servidor_cessao.servidor_cedido.get_vinculo()
            afastamento.tipo = self.servidor_cessao.tipo_afastamento
            afastamento.data_ini = self.data_inicial
            afastamento.data_fim = self.data_final
            afastamento.descricao = f'Conforme Processo Tipo {self.servidor_cessao.get_tipo_exercicio_display()}, tendo como Instituição de Destino o(a) {self.servidor_cessao.instituicao_destino}.'
            afastamento.save()
            #
            self.afastamento = afastamento
            self.save()

    def excluir_afastamento(self):
        if self.afastamento:
            if self.afastamento.delete():
                self.afastamento = None
                self.save()

    def delete(self, *args, **kwargs):
        self.excluir_afastamento()
        return super().delete(*args, **kwargs)


class Ato(models.ModelPlus):
    TIPO_ADMISSAO = 1
    TIPO_CONCESSAO_APOSENTADORIA = 2
    TIPO_CONCESSAO_PENSAO_CIVIL = 3
    TIPO_CHOICES = [
        [TIPO_ADMISSAO, 'Admissão de pessoal'],
        [TIPO_CONCESSAO_APOSENTADORIA, 'Concessão de aposentadoria'],
        [TIPO_CONCESSAO_PENSAO_CIVIL, 'Concessão de pensão civil'],
    ]

    SITUACAO_ENVIO_PENDENTE = 1
    SITUACAO_ENVIO_ENVIADO = 2
    SITUACAO_ENVIO_CANCELADO = 3
    SITUACAO_ENVIO_CHOICES = [
        [SITUACAO_ENVIO_PENDENTE, 'Pendente'],
        [SITUACAO_ENVIO_ENVIADO, 'Enviado'],
        [SITUACAO_ENVIO_CANCELADO, 'Cancelado'],
    ]

    SITUACAO_PRAZO_AINDA_NO_PRAZO = 1
    SITUACAO_PRAZO_ATRASADO = 2
    SITUACAO_PRAZO_ENVIAR_HOJE = 3
    SITUACAO_PRAZO_ENVIAR_ESTA_SEMANA = 4
    SITUACAO_PRAZO_ENVIAR_ESTE_MES = 5
    SITUACAO_PRAZO_CHOICES = [
        [SITUACAO_PRAZO_AINDA_NO_PRAZO, 'Ainda no prazo'],
        [SITUACAO_PRAZO_ATRASADO, 'Atrasado'],
        [SITUACAO_PRAZO_ENVIAR_HOJE, 'A ser enviado até hoje'],
        [SITUACAO_PRAZO_ENVIAR_ESTA_SEMANA, 'A ser enviado até esta semana'],
        [SITUACAO_PRAZO_ENVIAR_ESTE_MES, 'A ser enviado até este mês'],
    ]

    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    tipo = models.PositiveIntegerFieldPlus('Tipo de ato', choices=TIPO_CHOICES)
    data_ocorrencia = models.DateField('Data da ocorrência do ato')
    data_publicacao = models.DateField('Data da publicação do ato', blank=True, null=True)
    data_emissao = models.DateField('Data da emissão do ato', blank=True, null=True)
    numero = models.CharFieldPlus('Número do ato', blank=True, null=True)
    numero_doc_eletronico = models.CharFieldPlus('Número do documento eletrônico', blank=True, null=True)
    prazo_envio = models.PositiveIntegerFieldPlus('Prazo de envio ao E-Pessoal (em dias)')
    data_limite_envio = models.DateField('Data limite de envio do ato', editable=False, null=True)
    situacao_envio = models.PositiveIntegerFieldPlus('Situação de envio', choices=SITUACAO_ENVIO_CHOICES)
    data_envio = models.DateField('Data de envio do ato', blank=True, null=True)
    motivo_cancelamento = models.TextField('Motivo do cancelamento', null=True, blank=True)

    class Meta:
        verbose_name = 'Ato de Admissão/Concessão'
        verbose_name_plural = 'Atos de Admissão/Concessão'
        ordering = ('servidor__pessoa_fisica__nome',)

    def save(self, *args, **kwargs):
        is_add = not self.id

        if is_add or not self.prazo_envio:
            # popula o prazo de envio conforme última configuração do tipo de ato
            # dessa forma a configuração é replicada e pode continuar sofrendo alterações sem prejudicar
            # seus "consumidores antigos"
            # caso não haja nenhuma configuração para o tipo em questão, usa-se 1 dia de prazo (o mínimo possível
            # para não "quebrar" o save), o qual pode/deve ser editado via edição do Ato
            configuracao = TipoAtoConfiguracao.get_ultima_configuracao(tipo_ato=self.tipo)
            self.prazo_envio = configuracao.prazo_envio if configuracao else 1

        # calcula a data limite para o envio contando a partir da data de ocorrência do ato
        self.data_limite_envio = self.data_ocorrencia + timedelta(self.prazo_envio - 1)

        save = super().save(*args, **kwargs)
        return save

    def __str__(self):
        return '{}: {} - {}'.format(self.servidor, self.data_ocorrencia.strftime('%d/%m/%Y'), self.get_tipo_display())

    @staticmethod
    def get_atos(queryset_inicial=None, user_solicitante=None, servidor_alvo=None, tipo_ato=None, situacao_prazo=None):
        """retorna um queryset contendo 0 ou mais atos
        Ato.get_atos(sem parâmetros) -> equivale a Ato.objects.all()
        """
        atos = queryset_inicial or Ato.objects.all()

        if user_solicitante:
            solicitante_is_rh_campus = in_group(user_solicitante, 'Coordenador de Gestão de Pessoas')
            solicitante_is_rh_sistemico = in_group(user_solicitante, 'Coordenador de Gestão de Pessoas Sistêmico')
            solicitante_is_superuser = user_solicitante.is_superuser

            if not solicitante_is_superuser:
                if solicitante_is_rh_campus:
                    solicitante_campus = user_solicitante.get_relacionamento().setor.uo
                    atos = atos.filter(servidor__setor__uo__sigla=solicitante_campus.sigla)
                elif not solicitante_is_rh_sistemico:
                    atos = atos.none()

        if servidor_alvo:
            atos = atos.filter(servidor=servidor_alvo)

        if tipo_ato:
            atos = atos.filter(tipo=tipo_ato)

        try:
            situacao_prazo = int(situacao_prazo)
        except Exception:
            situacao_prazo = 0  # inválido

        if situacao_prazo:
            # apenas os pendentes
            atos = atos.filter(situacao_envio=Ato.SITUACAO_ENVIO_PENDENTE)

        hoje = date.today()

        if situacao_prazo == Ato.SITUACAO_PRAZO_AINDA_NO_PRAZO:
            atos = atos.filter(data_limite_envio__gte=hoje)

        elif situacao_prazo == Ato.SITUACAO_PRAZO_ATRASADO:
            atos = atos.filter(data_limite_envio__lt=hoje)

        elif situacao_prazo == Ato.SITUACAO_PRAZO_ENVIAR_HOJE:
            atos = atos.filter(data_limite_envio=hoje)

        elif situacao_prazo == Ato.SITUACAO_PRAZO_ENVIAR_ESTA_SEMANA:
            """
                d s t q q s s
                h           l

                l >= h
                l - h <= 6, l <= h + 6, l < h + 7
                p(l) > p(h)

                weekday datetime: 0 a 6
                week_day lookup.: 1 a 7
            """
            atos = atos.filter(
                data_limite_envio__gte=hoje, data_limite_envio__lt=hoje + timedelta(7), data_limite_envio__week_day__gte=hoje.weekday() + 1
            )

        elif situacao_prazo == Ato.SITUACAO_PRAZO_ENVIAR_ESTE_MES:
            atos = atos.filter(data_limite_envio__month=hoje.month, data_limite_envio__year=hoje.year)

        return atos

    @property
    def situacao_prazo(self):
        # podem ser múltiplas situações
        # Ex: esta semana pode conter mais de 1 mês e que "enviar esta semana" e "enviar este mês" pode ser verdadeiros
        situacao_prazo = []
        este_ato = Ato.objects.filter(id=self.id)

        for situacao_prazo_choice in Ato.SITUACAO_PRAZO_CHOICES:
            situacao_prazo_value = situacao_prazo_choice[0]
            if self in Ato.get_atos(queryset_inicial=este_ato, situacao_prazo=situacao_prazo_value):
                situacao_prazo.append(situacao_prazo_value)

        return situacao_prazo

    @property
    def is_envio_pendente(self):
        return self.situacao_envio == self.SITUACAO_ENVIO_PENDENTE

    ##
    # importação automática de atos
    # motivo original (conforme Demanda 615): popular atos de servidores oriundos do SIAPE

    class AtoImportado:
        TIPO_ATO_ADMISSAO_PESSOAL = 1
        TIPO_ATO_CONCESSAO_APOSENTADORIA = 2
        TIPO_ATO_CONCESSAO_PENSAO_CIVIL = 3

        def __init__(self, servidor_matricula, tipo_ato, data_ocorrencia, situacao_envio, data_envio):
            self.servidor_matricula = servidor_matricula
            self.tipo_ato = tipo_ato
            self.data_ocorrencia = data_ocorrencia  # date
            self.situacao_envio = situacao_envio
            self.data_envio = data_envio  # date ou None

        @classmethod
        def get_novo_ato_from_siape_ocorrencia_inicio_exercicio(
            cls, servidor_matricula, data_efetivo_exercicio, jah_enviado=False, data_envio_ao_e_pessoal=None
        ):
            """retorna uma instância de AtoImportado (ainda não persistente)

            Conforme Demanda 615:
                SIAPE: Início de Exercício - POSSE DE NOMEADO PARA CARGO EFETIVO"""

            return cls(
                servidor_matricula=servidor_matricula,
                tipo_ato=cls.TIPO_ATO_ADMISSAO_PESSOAL,
                data_ocorrencia=data_efetivo_exercicio,
                situacao_envio=Ato.SITUACAO_ENVIO_ENVIADO if jah_enviado else Ato.SITUACAO_ENVIO_PENDENTE,
                data_envio=data_envio_ao_e_pessoal,
            )

        @classmethod
        def get_novo_ato_from_siape_ocorrencia_aposentadoria_voluntaria(
            cls, servidor_matricula, data_ocorrencia_aposentadoria, jah_enviado=False, data_envio_ao_e_pessoal=None
        ):
            """retorna uma instância de AtoImportado (ainda não persistente)

            Conforme Demanda 615:
                SIAPE: APOSENTADORIA VOLUNTARIA - 05244 - APOSENTADORIA"""

            return cls(
                servidor_matricula=servidor_matricula,
                tipo_ato=cls.TIPO_ATO_CONCESSAO_APOSENTADORIA,
                data_ocorrencia=data_ocorrencia_aposentadoria,
                situacao_envio=Ato.SITUACAO_ENVIO_ENVIADO if jah_enviado else Ato.SITUACAO_ENVIO_PENDENTE,
                data_envio=data_envio_ao_e_pessoal,
            )

        @classmethod
        def get_novo_ato_from_siape_ocorrencia_falecimento(
            cls, servidor_matricula, data_ocorrencia_falecimento, jah_enviado=False, data_envio_ao_e_pessoal=None
        ):
            """retorna uma instância de AtoImportado (ainda não persistente)

            Conforme Demanda 615:
                SIAPE: FALECIMENTO - 02007 - EXCLUSAO"""

            return cls(
                servidor_matricula=servidor_matricula,
                tipo_ato=cls.TIPO_ATO_CONCESSAO_PENSAO_CIVIL,
                data_ocorrencia=data_ocorrencia_falecimento,
                situacao_envio=Ato.SITUACAO_ENVIO_ENVIADO if jah_enviado else Ato.SITUACAO_ENVIO_PENDENTE,
                data_envio=data_envio_ao_e_pessoal,
            )

    @staticmethod
    def importa_atos(lista_atos, atualizar_atos_jah_existentes=False):
        """lista_atos: lista de instâncias de AtoImportado
        retorna uma lista de instâncias de Ato (já persistentes)

        Exemplo de utilização:
            ato1 = Ato.AtoImportado.get_novo_ato_from_siape_ocorrencia_inicio_exercicio(
                servidor_matricula='9999999',
                data_efetivo_exercicio=datetime.date(ano, mes, dia),
                jah_enviado=True,
                data_envio_ao_e_pessoal=datetime.date(ano, mes, dia)
            )
            ato2 = Ato.AtoImportado.get_novo_ato_from_siape_ocorrencia_aposentadoria_voluntaria(
                servidor_matricula='9999999',
                data_ocorrencia_aposentadoria=datetime.date(ano, mes, dia),
                jah_enviado=True,
                data_envio_ao_e_pessoal=datetime.date(ano, mes, dia)
            )
            ato3 = Ato.AtoImportado.get_novo_ato_from_siape_ocorrencia_falecimento(
                servidor_matricula='9999999',
                data_ocorrencia_falecimento=datetime.date(ano, mes, dia),
                jah_enviado=True,
                data_envio_ao_e_pessoal=datetime.date(ano, mes, dia)
            )

            novos_atos = Ato.importa_atos([ato1, ato2, ato3])
            atos_atualizados = Ato.importa_atos([ato1], atualizar_atos_jah_existentes=True)
        """

        atos_gravados = []

        for ato_a_importar in lista_atos:
            servidor = Servidor.objects.filter(matricula=ato_a_importar.servidor_matricula)

            try:
                tipo_ato = int(ato_a_importar.tipo_ato)
                tipo_ato_is_valido = tipo_ato in [choice[0] for choice in Ato.TIPO_CHOICES]
            except Exception:
                tipo_ato = 0
                tipo_ato_is_valido = False

            if servidor.exists() and tipo_ato_is_valido:
                servidor = servidor.first()
                data_ocorrencia = ato_a_importar.data_ocorrencia
                tipo_ato_ultima_configuracao = TipoAtoConfiguracao.get_ultima_configuracao(tipo_ato=tipo_ato)

                ato = Ato.objects.filter(servidor=servidor, tipo=tipo_ato, data_ocorrencia=data_ocorrencia)

                if ato.exists():
                    if atualizar_atos_jah_existentes:
                        ato = ato.first()
                        ato.servidor = servidor
                        ato.tipo = tipo_ato
                        ato.data_ocorrencia = data_ocorrencia
                        ato.prazo_envio = tipo_ato_ultima_configuracao.prazo_envio
                        ato.situacao_envio = ato_a_importar.situacao_envio
                        ato.data_envio = ato_a_importar.data_envio

                        ato.save()
                        atos_gravados.append(ato)
                else:
                    ato = Ato(
                        servidor=servidor,
                        tipo=tipo_ato,
                        data_ocorrencia=data_ocorrencia,
                        prazo_envio=tipo_ato_ultima_configuracao.prazo_envio,
                        situacao_envio=ato_a_importar.situacao_envio,
                        data_envio=ato_a_importar.data_envio,
                    )

                    ato.save()
                    atos_gravados.append(ato)

        return atos_gravados


class TipoAtoConfiguracao(models.ModelPlus):
    """informações extras e editáveis sobre os tipos constantes de atos"""

    tipo_ato = models.PositiveIntegerFieldPlus('Tipo de ato', choices=Ato.TIPO_CHOICES)
    descricao = models.TextField('Descrição', null=True, blank=True)
    prazo_envio = models.PositiveIntegerFieldPlus('Prazo de envio ao E-Pessoal (em dias)', default=60)

    class Meta:
        verbose_name = 'Configuração de Tipo de Ato de Admissão/Concessão'
        verbose_name_plural = 'Configurações de Tipos de Atos de Admissão/Concessão'
        ordering = ('-id',)

    def __str__(self):
        return '{} - {}Prazo de envio (em dias): {}'.format(
            self.get_tipo_ato_display(), f'{self.descricao} ' if self.descricao else '', self.prazo_envio
        )

    @staticmethod
    def get_ultima_configuracao(tipo_ato):
        tipo_ato_ultima_configuracao = TipoAtoConfiguracao.objects.filter(tipo_ato=tipo_ato).order_by('-id').first()

        if not tipo_ato_ultima_configuracao:
            tipo_ato_ultima_configuracao = TipoAtoConfiguracao(
                tipo_ato=tipo_ato,
                prazo_envio=60,  # um valor padrão conforme Demanda 615
            )
            tipo_ato_ultima_configuracao.save()

        return tipo_ato_ultima_configuracao
