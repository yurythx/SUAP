import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from numpy import arange

from djtools.db import models
from djtools.db.models import Q
from djtools.templatetags.filters import in_group
from djtools.utils import datas_entre, get_datetime_now, periodos_sucessivos, send_notification

if TYPE_CHECKING:
    from comum.models import User


class CargaHorariaReduzida(models.ModelPlus):
    TIPO_AFASTAMENTO_PARCIAL = 0
    TIPO_CH_EXCEPCIONAL = 1

    STATUS_AGUARDANDO_VALIDACAO_CHEFE = 0
    STATUS_AGUARDANDO_VALIDACAO_RH = 1
    STATUS_DEFERIDO_PELO_RH = 2
    STATUS_INDEFERIDO_PELO_RH = 3
    STATUS_INDEFERIDO_PELO_CHEFE = 4
    STATUS_NOVOS_DOCUMENTOS_SOLICITADOS = 5
    STATUS_AGUARDANDO_ENVIO_CHEFE = 6
    STATUS_ALTERANDO_HORARIO = 7
    STATUS_AGUARDANDO_CADASTRAR_HORARIO = 8
    STATUS_HORARIO_CADASTRADO = 9

    STATUS_AMIGAVEL_DEFERIDO = 'deferir'
    STATUS_AMIGAVEL_INDEFERIDO = 'indeferir'
    STATUS_AMIGAVEL_SOLICITAR_DOCUMENTOS = 'solicitardocumentos'

    STATUS_AMIGAVEL_CHOICES = [
        [STATUS_AMIGAVEL_DEFERIDO, 'Deferir'],
        [STATUS_AMIGAVEL_INDEFERIDO, 'Indeferir'],
        [STATUS_AMIGAVEL_SOLICITAR_DOCUMENTOS, 'Solicitar documentos'],
    ]

    TIPO_CHOICES = [[TIPO_AFASTAMENTO_PARCIAL, 'Afastamento parcial'], [TIPO_CH_EXCEPCIONAL, 'Carga horária excepcional']]
    STATUS_CHOICES = [
        [STATUS_AGUARDANDO_VALIDACAO_CHEFE, 'Aguardando validação do chefe'],
        [STATUS_AGUARDANDO_VALIDACAO_RH, 'Aguardando validação do RH'],
        [STATUS_DEFERIDO_PELO_RH, 'Deferido'],
        [STATUS_INDEFERIDO_PELO_RH, 'Indeferido'],
        [STATUS_INDEFERIDO_PELO_CHEFE, 'Indeferido pelo chefe'],
        [STATUS_NOVOS_DOCUMENTOS_SOLICITADOS, 'Novos documentos solicitados pelo RH'],
        [STATUS_AGUARDANDO_ENVIO_CHEFE, 'Aguardando envio para o chefe'],
        [STATUS_ALTERANDO_HORARIO, 'Alterando horário'],
        [STATUS_AGUARDANDO_CADASTRAR_HORARIO, 'Aguardando cadastrar horário'],
        [STATUS_HORARIO_CADASTRADO, 'Horário cadastrado'],
    ]

    protocolo_content_type = models.ForeignKeyPlus(ContentType, on_delete=models.CASCADE, null=True, blank=False, default=None)
    protocolo_content_id = models.PositiveIntegerField(verbose_name='Protocolo (Id)', default=0)
    protocolo_content_object = GenericForeignKey('protocolo_content_type', 'protocolo_content_id')

    servidor = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    chefe_imediato_validador = models.ForeignKeyPlus(
        'rh.Servidor', null=True, blank=True, related_name='chefe_imediato_validador', on_delete=models.CASCADE
    )
    servidor_rh_validador = models.ForeignKeyPlus(
        'rh.Servidor', null=True, blank=True, related_name='servidor_rh_validador', verbose_name='Validador', on_delete=models.CASCADE
    )
    numero = models.IntegerField('Número do Processo', blank=True, null=True)
    data_inicio = models.DateFieldPlus('Início da Alteração', blank=False, null=True)
    data_termino = models.DateFieldPlus('Término da Alteração', blank=False, null=True)
    tipo = models.IntegerField(choices=TIPO_CHOICES)
    status = models.IntegerField('Situação do Processo', choices=STATUS_CHOICES)
    nova_jornada = models.CharFieldPlus('Nova Jornada de Trabalho', blank=True, null=True)
    ano = models.IntegerField()
    motivo_indeferimento_chefe = models.CharField('Motivo do Indeferimento', max_length=2000, blank=False, null=True)
    motivo_indeferimento_rh = models.CharField('Motivo do Indeferimento', max_length=2000, blank=False, null=True)
    descricao_novos_documentos = models.CharField('Descrição dos novos documentos', max_length=2000, blank=False, null=True)

    class Meta:
        verbose_name = 'Processo de Alteração de Carga Horária'
        verbose_name_plural = 'Processos de Alteração de Carga Horária'

    def __str__(self):
        return f'Processo de Alteração de Carga Horária - {self.servidor}'

    @property
    def status_estilizado(self):
        class_css = 'status-error'
        status_display = self.get_status_display()

        if self.status == CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_CHEFE:
            class_css = 'status-em-tramite'
        if self.status == CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH:
            class_css = 'status-em-tramite'
        if self.status == CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_CHEFE:
            class_css = 'status-rejeitado'
        if self.status == CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH:
            class_css = 'status-rejeitado'
        if self.status == CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH:
            class_css = 'status-success'
        if self.status == CargaHorariaReduzida.STATUS_NOVOS_DOCUMENTOS_SOLICITADOS:
            class_css = 'status-alert'
        return f"<span class='status {class_css} text-nowrap-normal'>{status_display}</span>"

    @staticmethod
    def format_ch(ch_float):
        if ch_float > 0:
            ch_h = int(ch_float)
            ch_min = round(60 * (ch_float - float(ch_h)))
            if ch_min < 10:
                ch_min = f'0{ch_min}'
            return f'{ch_h}:{ch_min}'
        return '0:00'

    def get_carga_horaria_disponivel_choice(self, diaria: bool = False) -> list[list[float | str]]:
        # Máximo que um servidor pode trabalhar por dia é 10h
        # Jornada fora dos nomes conhecidos devolve None (diária): assume 8h/dia (40h semanais)
        opcao_maximo = 10.0 if diaria else (self.servidor.jornada_trabalho.get_jornada_trabalho_diaria() or 8) * 5
        passo = 0.5
        lista_carga = [[i, f'{self.format_ch(i)} SEMANAL '] for i in arange(0, opcao_maximo + passo, passo)]
        return lista_carga

    """
    editar: o servidor pode editar antes de enviar o processo para validação do chefe
    """

    def servidor_pode_editar(self):
        return self.status == self.STATUS_AGUARDANDO_ENVIO_CHEFE

    def processo_editavel(self):
        return self.status == self.STATUS_AGUARDANDO_ENVIO_CHEFE or self.status == self.STATUS_NOVOS_DOCUMENTOS_SOLICITADOS

    def servidor_pode_enviar_novos_documentos(self):
        return self.status == self.STATUS_NOVOS_DOCUMENTOS_SOLICITADOS

    def status_processo_indeferido_pelo_rh(self):
        return self.status == self.STATUS_INDEFERIDO_PELO_RH

    def status_documentos_solicitados(self):
        return self.status == self.STATUS_NOVOS_DOCUMENTOS_SOLICITADOS

    @staticmethod
    def servidor_tem_funcao(servidor):
        return servidor.funcao

    @staticmethod
    def setor_servidor_eh_flexivel(servidor):
        jonada_trabalho_setor = servidor.setor.jornada_trabalho()
        return jonada_trabalho_setor.nome == '30 HORAS SEMANAIS'

    def chefe_pode_validar(self):
        return self.status == self.STATUS_AGUARDANDO_VALIDACAO_CHEFE

    def rh_pode_validar(self):
        return (
            self.status == self.STATUS_AGUARDANDO_VALIDACAO_RH
            or self.status == self.STATUS_DEFERIDO_PELO_RH
            or self.status == self.STATUS_ALTERANDO_HORARIO
        )

    def status_deferido(self):
        return self.status == self.STATUS_DEFERIDO_PELO_RH

    def rh_pode_editar_horario(self):
        return self.status == self.STATUS_AGUARDANDO_VALIDACAO_RH or self.status != self.STATUS_DEFERIDO_PELO_RH

    def pode_atualizar_situacao_pelo_rh(self) -> bool:
        """O RH pode deferir ou indeferir o afastamento parcial (``alterar_situacao_afastamento_parcial_rh``): pode
        validar e o processo ainda não foi deferido, então nem re-defere nem reverte um deferido.

        É a regra do botão "Atualizar Situação" da tela do processo. A carga horária excepcional não passa por ele: tem
        os botões "Deferir" (``pode_deferir_ch_excepcional``) e "Indeferir" (``pode_indeferir_ch_excepcional``).
        """
        return self.tipo_afastamento_parcial() and self.rh_pode_validar() and self.rh_pode_editar_horario()

    def pode_deferir_ch_excepcional(self) -> bool:
        """O RH pode deferir a carga horária excepcional (POST ``salvar_ch_excepcional`` da tela do processo).

        É a regra do botão "Deferir" da tela: carga horária excepcional ainda não decidida. A decisão do RH é final:
        nem o deferido é deferido de novo, nem o indeferido é revertido (#17729).
        """
        return self.tipo_ch_excepcional() and not self.status_deferido() and not self.status_processo_indeferido_pelo_rh()

    def pode_indeferir_ch_excepcional(self) -> bool:
        """O RH pode indeferir a carga horária excepcional (POST ``indeferir_ch_excepcional`` da tela do processo).

        É a regra do botão "Indeferir" da tela, a mesma do "Deferir": só a carga horária excepcional ainda não decidida.
        """
        return self.pode_deferir_ch_excepcional()

    def deferir_pelo_rh(self, user: User) -> None:
        """Defere o processo pelo RH: registra o ``user`` como validador e notifica o servidor.

        É o único caminho de deferimento, do afastamento parcial e da carga horária excepcional; quem chama confere a
        permissão (``pode_atualizar_situacao_pelo_rh``/``pode_deferir_ch_excepcional``) e os horários.
        """
        self.status = self.STATUS_DEFERIDO_PELO_RH
        self.servidor_rh_validador = user.get_relacionamento()
        self.save()
        assunto = '[SUAP] Processo de Alteração de Carga Horária'
        mensagem = '''"Seu processo de alteração de carga horária foi deferido pelo RH "'''
        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [self.servidor.get_vinculo()])

    def indeferir_pelo_rh(self, user: User, motivo: str) -> None:
        """Indefere o processo pelo RH: registra o ``user`` como validador e o ``motivo``, e notifica o servidor.

        É o único caminho de indeferimento pelo RH, do afastamento parcial e da carga horária excepcional; quem chama
        confere a permissão (``pode_atualizar_situacao_pelo_rh``/``pode_indeferir_ch_excepcional``) e o motivo.
        """
        self.status = self.STATUS_INDEFERIDO_PELO_RH
        self.servidor_rh_validador = user.get_relacionamento()
        self.motivo_indeferimento_rh = motivo
        self.save()
        assunto = '[SUAP] Processo de Alteração de Carga Horária'
        mensagem = '''"Seu processo de alteração de carga horária foi indeferido pelo RH "'''
        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [self.servidor.get_vinculo()])

    def obter_emails_chefes(self):
        emails = []
        for chefe in self.chefe:
            emails.append(chefe.email_notificacao)
        return emails

    def tipo_afastamento_parcial(self):
        return self.tipo == self.TIPO_AFASTAMENTO_PARCIAL

    def tipo_ch_excepcional(self):
        return self.tipo == self.TIPO_CH_EXCEPCIONAL

    @property
    def chefe(self):
        return self.servidor.chefes_na_data(data=get_datetime_now())

    @staticmethod
    def get_processos_afastamento_aguardando_validacao(chefe_imediato_validador):
        processos_afastamento_ids = []
        for processo_afastamento in CargaHorariaReduzida.objects.filter(status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_CHEFE):
            if chefe_imediato_validador.id in [chefe.id for chefe in processo_afastamento.chefe]:
                processos_afastamento_ids.append(processo_afastamento.id)
        return CargaHorariaReduzida.objects.filter(id__in=processos_afastamento_ids)

    @staticmethod
    def filtro_escopo_rh(user: User) -> Q:
        """Processos que o RH do usuário alcança, como filtro: todos para o superusuário e o RH sistêmico; para o RH do
        campus ("Coordenador de Gestão de Pessoas"), os de servidor lotado no campus do usuário; nenhum para os demais.

        É o critério da listagem do admin (``CargaHorariaReduzidaAdmin.regras_filtro_queryset``), que as telas e ações
        do processo repetem via ``no_escopo_do_rh``.
        """
        if in_group(user, 'Coordenador de Gestão de Pessoas Sistêmico'):
            return Q()
        setor = user.get_relacionamento().setor if in_group(user, 'Coordenador de Gestão de Pessoas') else None
        if setor is None or setor.uo is None:
            return Q(pk__in=[])
        return Q(servidor__setor__uo__sigla=setor.uo.sigla)

    def no_escopo_do_rh(self, user: User) -> bool:
        """O processo está entre os que o RH do usuário alcança (``filtro_escopo_rh``)."""
        return CargaHorariaReduzida.objects.filter(CargaHorariaReduzida.filtro_escopo_rh(user), pk=self.pk).exists()

    @staticmethod
    def get_processos_rh_a_validar(user: User) -> models.QuerySet[CargaHorariaReduzida]:
        return CargaHorariaReduzida.objects.filter(
            CargaHorariaReduzida.filtro_escopo_rh(user), status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH
        )

    def validar_periodos_horarios(self):
        periodos_horarios = []
        menor_data = None
        maior_data = None
        for periodo in self.horariosemanal_set.all():
            periodos_horarios += ((periodo.data_inicio, periodo.data_fim),)

            if not menor_data:
                menor_data = periodo.data_inicio
            if not maior_data:
                maior_data = periodo.data_fim

            if periodo.data_inicio < menor_data:
                menor_data = periodo.data_inicio
            if periodo.data_fim > maior_data:
                maior_data = periodo.data_fim

        if periodos_horarios:
            if self.data_inicio < menor_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período de horário não coberto: {} a {}.'.format(
                        self.data_inicio.strftime('%d/%m/%Y'), (menor_data - datetime.timedelta(1)).strftime('%d/%m/%Y')
                    ),
                )
            #
            elif self.data_inicio > menor_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período de horário inválido: {} a {}.'.format(
                        menor_data.strftime('%d/%m/%Y'), (self.data_inicio - datetime.timedelta(1)).strftime('%d/%m/%Y')
                    ),
                )

            elif self.data_termino > maior_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período de horário não coberto: {} a {}.'.format(
                        (maior_data + datetime.timedelta(1)).strftime('%d/%m/%Y'), self.data_termino.strftime('%d/%m/%Y')
                    ),
                )
            #
            elif self.data_termino < maior_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período de horário inválido: {} a {}.'.format(
                        (self.data_termino + datetime.timedelta(1)).strftime('%d/%m/%Y'), maior_data.strftime('%d/%m/%Y')
                    ),
                )
            else:
                periodos_ok, periodos_mensagem = periodos_sucessivos(periodos_horarios)
                periodos_mensagem = ''.join(periodos_mensagem)
                #
                if not periodos_ok:
                    periodos_mensagem = 'Existem períodos/dias descobertos entre os períodos informados ou períodos sobrepostos'

        return periodos_ok, periodos_mensagem

    @staticmethod
    def get_processos_deferidos(servidor, data=None):
        processos = CargaHorariaReduzida.objects.filter(status=CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, servidor=servidor)
        if data:
            processos = processos.filter(data_inicio__lte=data, data_termino__gte=data)
        return processos

    @staticmethod
    def existe_processos_deferidos(servidor, data=None):
        return CargaHorariaReduzida.get_processos_deferidos(servidor, data).exists()

    @staticmethod
    def get_processos_deferidos_por_periodo(servidor, data_inicio, data_fim):
        processos = CargaHorariaReduzida.objects.filter(
            Q(
                servidor=servidor,
                status=CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH,
            )
            & Q(
                # data de inicio do processo dentro do período informado
                Q(data_inicio__gte=data_inicio, data_inicio__lte=data_fim)
                # data de fim do processo dentro do período informado
                | Q(data_termino__gte=data_inicio, data_termino__lte=data_fim)
                # data de inicio do processo antes do período informado e data fim do processo depois da data de inicio do período informado
                | Q(data_inicio__lt=data_inicio, data_termino__gte=data_inicio)
            )
        )
        return processos

    def pode_ser_excluido_por(self, user: User) -> bool:
        """Só o próprio servidor exclui o processo, e enquanto ainda pode editá-lo (antes de enviar ao chefe).

        É a regra do ícone de exclusão da listagem (``CargaHorariaReduzidaAdmin.opcoes``). O dono é conferido pelo
        vínculo: o ``id`` da pessoa física não é o do ``Servidor``.
        """
        return self.servidor_pode_editar() and user.get_vinculo() == self.servidor.get_vinculo()

    def pode_anexar_documento(self, user: User) -> bool:
        """Quem anexa e exclui documento do processo: quem vê o uploader da tela do processo (``abrir_processo_afastamento_parcial``).

        A tela só abre para o RH no escopo do processo (``no_escopo_do_rh``) e só mostra o uploader no afastamento parcial.
        O dono não exclui documento (#17705): nem vê a tela.
        """
        return self.tipo_afastamento_parcial() and self.no_escopo_do_rh(user)

    def pode_ver_documentos(self, user: User) -> bool:
        """Quem abre os documentos anexados: o próprio servidor, pelo vínculo, e o RH no escopo do processo, que vê os links na tela."""
        return user.get_vinculo() == self.servidor.get_vinculo() or self.no_escopo_do_rh(user)

    def pode_alterar_horario(self, user: User, acao: str) -> bool:
        """Quem adiciona (``acao='adicionar'``), edita (``'editar'``) ou remove (``'remover'``) horário semanal do processo.

        É a regra do botão "Adicionar Horário" e dos ícones de editar e remover na tela do processo
        (``abrir_processo_afastamento_parcial``), que só abre para os coordenadores de Gestão de Pessoas: valem com o
        servidor ainda podendo editar, na carga horária excepcional e ao RH sistêmico; ao RH do campus, enquanto o RH
        pode validar (adicionar) ou editar o horário (editar e remover). Adicionar e remover ainda exigem a situação
        em que as views sempre aceitaram a alteração. O RH do campus só alcança processo de servidor do seu campus
        (``no_escopo_do_rh``).
        """
        if not self.no_escopo_do_rh(user):
            return False
        eh_rh_sistemico = user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
        eh_rh_campus = user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)
        rh_campus_alcanca = self.rh_pode_validar() if acao == 'adicionar' else self.rh_pode_editar_horario()
        pela_tela = self.servidor_pode_editar() or self.tipo_ch_excepcional() or eh_rh_sistemico or eh_rh_campus and rh_campus_alcanca
        situacao_aceita = acao == 'editar' or self.servidor_pode_editar() or self.rh_pode_validar() or self.tipo_ch_excepcional()
        return pela_tela and situacao_aceita


class DocumentacaoExigida(models.EncryptedPKModel):
    processo = models.ForeignKeyPlus(
        'rh.CargaHorariaReduzida',
        blank=True,
        null=False,
        verbose_name='processo associado ao arquivo',
        related_name='documentos',
        on_delete=models.CASCADE,
    )
    nome = models.CharFieldPlus(max_length=255)
    diretorio = models.CharFieldPlus(max_length=255, unique=True)
    tamanho = models.BigIntegerField()

    objects = models.EncryptedPKModelManager()


class HorarioSemanal(models.ModelPlus):
    processo_reducao_ch = models.ForeignKeyPlus(
        'rh.CargaHorariaReduzida', blank=True, null=False, verbose_name='Processo de afastamento', on_delete=models.CASCADE
    )
    data_inicio = models.DateFieldPlus('Data Inicial')
    data_fim = models.DateFieldPlus('Data Final', null=True)
    seg = models.FloatField('SEG', blank=False, null=False)
    ter = models.FloatField('TER', blank=False, null=False)
    qua = models.FloatField('QUA', blank=False, null=False)
    qui = models.FloatField('QUI', blank=False, null=False)
    sex = models.FloatField('SEX', blank=False, null=False)
    jornada_semanal = models.CharFieldPlus('Jornada de Trabalho', blank=True, null=True)

    class Meta:
        ordering = ('data_inicio',)
        verbose_name = 'Horário de Afasmento'
        verbose_name_plural = 'Horários de Afastamento'

    def __str__(self):
        return f'Horário do Afastamento - {self.processo_reducao_ch.servidor}'

    @property
    def seg_format_ch(self):
        return CargaHorariaReduzida.format_ch(self.seg)

    @property
    def ter_format_ch(self):
        return CargaHorariaReduzida.format_ch(self.ter)

    @property
    def qua_format_ch(self):
        return CargaHorariaReduzida.format_ch(self.qua)

    @property
    def qui_format_ch(self):
        return CargaHorariaReduzida.format_ch(self.qui)

    @property
    def sex_format_ch(self):
        return CargaHorariaReduzida.format_ch(self.sex)

    @property
    def jornada_semanal_format_ch(self):
        return CargaHorariaReduzida.format_ch(float(self.jornada_semanal))

    @staticmethod
    def get_jornadas_servidor_horario(servidor, data_inicio, data_fim):
        from .jornada_trabalho import JornadaTrabalhoPersonalizada

        jornadas_trabalho_servidor = {}

        processos_ch_reduzida = CargaHorariaReduzida.get_processos_deferidos(servidor)

        # ordena os processos de ch excepcional do mais antigo para o mais recente de modo que os
        # dias em conflito receberão a informação do último processo, ou seja, do mais recente
        processos_ch_reduzida = processos_ch_reduzida.order_by('data_inicio')

        horarios_semanais = HorarioSemanal.objects.filter(data_inicio__lte=data_fim, data_fim__gte=data_inicio)

        for processo in processos_ch_reduzida:
            processo_horarios_semanais = horarios_semanais.filter(processo_reducao_ch=processo)
            for horario_semanal in processo_horarios_semanais:
                for dia in datas_entre(horario_semanal.data_inicio, horario_semanal.data_fim):
                    if data_inicio <= dia <= data_fim:
                        ch_dia = None

                        if dia.weekday() == 0:
                            ch_dia = horario_semanal.seg
                        elif dia.weekday() == 1:
                            ch_dia = horario_semanal.ter
                        elif dia.weekday() == 2:
                            ch_dia = horario_semanal.qua
                        elif dia.weekday() == 3:
                            ch_dia = horario_semanal.qui
                        elif dia.weekday() == 4:
                            ch_dia = horario_semanal.sex

                        if ch_dia is not None:
                            jornadas_trabalho_servidor[dia] = JornadaTrabalhoPersonalizada(ch_dia, float(horario_semanal.jornada_semanal))

        return jornadas_trabalho_servidor
