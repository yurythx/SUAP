import datetime

from dateutil.parser import parse
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from comum.models import UsuarioGrupo
from djtools.db import models
from edu.managers import FiltroPoloManager
from edu.models.cadastros_gerais import Turno
from edu.models.logs import LogModel


class OpcaoAcessibilidadePolo(models.ModelPlus):
    descricao = models.CharField(verbose_name='Descrição', max_length=255)

    class Meta:
        verbose_name = 'Opção de Acessibilidade dos Polos'
        verbose_name_plural = 'Opções de Acessibilidade dos Polos'
        ordering = ['descricao']

    def __str__(self):
        return self.descricao


class TecnologiaEquipamentoPolo(models.ModelPlus):
    descricao = models.CharField(verbose_name='Descrição', max_length=255)

    class Meta:
        verbose_name = 'Tecnologia/Equipamento dos Polos'
        verbose_name_plural = 'Tecnologias/Equipamentos dos Polos'
        ordering = ['descricao']

    def __str__(self):
        return self.descricao


class TipoPolo(models.Model):
    descricao = models.CharField(verbose_name='Descrição')

    class Meta:
        verbose_name = 'Tipo de Polo'
        verbose_name_plural = 'Tipos de Polos'

    def __str__(self):
        return self.descricao


class Polo(LogModel):
    tipo = models.ForeignKey(TipoPolo, verbose_name='Tipo', on_delete=models.CASCADE, null=True)
    descricao = models.CharFieldPlus('Nome')
    sigla = models.CharFieldPlus('Sigla')
    cidade = models.ForeignKeyPlus('edu.Cidade', verbose_name='Cidade', null=True)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)
    arquivo_autorizacao = models.FileFieldPlus(
        verbose_name='Projeto de Polo de Educação a Distância', upload_to='autorizacao_polo', filetypes=['pdf'], null=True, blank=True
    )

    # códigos
    codigo_censup = models.CharFieldPlus('Código CENSUP', default='', blank=True)
    codigo_sistec = models.CharFieldPlus('Código SISTEC', default='', blank=True)
    codigo_sisuab = models.CharFieldPlus('Código SisUAB', default='', blank=True)
    codigo_emec = models.CharFieldPlus('Código EMEC', default='', blank=True)
    codigo_academico = models.IntegerField('Código Acadêmico', null=True)

    estrutura_disponivel = models.TextField('Estrutura Disponível', null=True, blank=True)
    # endereco
    logradouro = models.CharFieldPlus('Logradouro', max_length=255, null=True, blank=True)
    numero = models.CharFieldPlus('Número', max_length=255, null=True, blank=True)
    complemento = models.CharFieldPlus('Complemento', max_length=255, null=True, blank=True)
    bairro = models.CharFieldPlus('Bairro', max_length=255, null=True, blank=True)
    cep = models.CharFieldPlus('CEP', max_length=255, null=True, blank=True)
    # dados específicos
    do_municipio = models.BooleanField('Polo do Município', default=False)
    diretoria = models.ForeignKeyPlus('edu.Diretoria', verbose_name='Diretoria Acadêmica', null=True, blank=False)
    # telefones
    telefone_principal = models.CharFieldPlus('Telefone Principal', max_length=255, null=True, blank=True)
    telefone_secundario = models.CharFieldPlus('Telefone Secundário', max_length=255, null=True, blank=True)
    campus_atendimento = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus de Atendimento', null=True, blank=True)

    # Acessibilidade
    opcoes_acessibilidade = models.ManyToManyField(OpcaoAcessibilidadePolo, verbose_name='Opcões de Acessibilidade', blank=True)
    rampa_acesso_corrimao = models.CharField(
        verbose_name='Rampa de acesso com corrimão?',
        choices=[['Sim', 'Sim'], ['Não', 'Não'], ['Não se aplica', 'Não se aplica']],
        null=True,
        blank=True,
        max_length=25,
    )
    equipamentos_eletronicos = models.CharField(
        verbose_name='Equipamento eletromecânico?',
        choices=[['Sim', 'Sim'], ['Não', 'Não'], ['Não se aplica', 'Não se aplica']],
        null=True,
        blank=True,
        help_text='Elevadores, esteiras rolantes, entre outros.',
        max_length=25,
    )

    # Tecnologias/Equipamentos
    tecnologias_equipamentos = models.ManyToManyField(TecnologiaEquipamentoPolo, verbose_name='Tecnologias/Equipamentos Disponíveis', blank=True)
    qtd_computadores_discentes = models.IntegerField(verbose_name='Quantidade de Computadores para Discentes', null=True, blank=True)

    tipo_local_matricula = models.IntegerField(
        verbose_name='Local de Matrícula', choices=[[1, 'Polo'], [2, 'Campus'], [3, 'Outro']], null=True, blank=True
    )
    especificacao_local_matricula = models.CharField(
        verbose_name='Especificação do Local de Matrícula',
        max_length=255,
        help_text='Informar no caso do local de matrícula não ser nem o campus e nem o polo.',
        null=True,
        blank=True,
    )

    objects = models.Manager()
    locals = FiltroPoloManager('diretoria')

    class Meta:
        verbose_name = 'Polo EAD'
        verbose_name_plural = 'Polos EAD'

    def get_coordenador_titular(self):
        qs = self.coordenadorpolo_set.filter(titular=True)
        return qs and qs[0] or None

    def get_proximas_atividades(self):
        return self.atividadepolo_set.filter(data_inicio__gte=datetime.datetime.now()).order_by('data_inicio').order_by('data_fim')

    def definiu_horario(self):
        return self.horariofuncionamentopolo_set.exists()

    def get_tutores(self, curso_campus):
        return self.tutorpolo_set.filter(cursos=curso_campus)

    def get_cursos_ofertados(self):
        from edu.models import CursoCampus

        return CursoCampus.objects.filter(aluno__polo=self).distinct()

    def get_endereco(self):
        if self.logradouro:
            return '{}, {}, {}, {}, {}, {}'.format(
                self.logradouro or '-', self.numero or '-', self.complemento or '-', self.bairro or '-', self.cep or '-', self.cidade or '-'
            )
        else:
            return None

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/edu/polo/{self.id}'

    def get_horarios_por_turno(self, turno=None):
        if turno:
            turnos_ids = [turno.pk]
        else:
            if self.horariofuncionamentopolo_set.exists():
                turnos_ids = HorarioFuncionamentoPolo.objects.filter(polo=self).values_list('turno__id', flat=True).distinct()
            else:
                turnos_ids = []
        dias_semana = HorarioTutorPolo.DIA_SEMANA_CHOICES
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')

        for turno in turnos:
            turno.horarios = []
            turno.dias_semana = dias_semana
            for horario in turno.horariofuncionamentopolo_set.filter(polo=self):
                horario.dias_semana = []
                for dia_semana in dias_semana:
                    numero = dia_semana[0]
                    nome = dia_semana[1]
                    qs = self.horariopolo_set.filter(dia_semana=dia_semana[0], horario_funcionamento=horario)
                    marcado = qs.count()
                    tutores = HorarioTutorPolo.objects.filter(horario_funcionamento=horario, dia_semana=dia_semana[0]).values_list(
                        'tutor__vinculo__pessoa__nome', flat=True
                    )
                    coordenadores = HorarioCoordenadorPolo.objects.filter(horario_funcionamento=horario, dia_semana=dia_semana[0]).values_list(
                        'coordenador__vinculo__pessoa__nome', flat=True
                    )
                    if qs.exists():
                        qs = qs[0]
                    else:
                        qs = None
                    horario.dias_semana.append(
                        {
                            'numero': numero,
                            'nome': nome,
                            'marcado': marcado,
                            'horario_aula_diario': qs,
                            'tutores': tutores,
                            'coordenadores': coordenadores,
                        }
                    )
                turno.horarios.append(horario)
        return turnos

    def get_atos_regulatorios(self):
        return self.atoregulatoriopolo_set.order_by('data_publicacao')


class AtoRegulatorioPolo(LogModel):
    TIPO_DOCUMENTO_CHOICES = [('resolucao', 'Resolução'), ('deliberacao', 'Deliberação'), ('portaria_mec', 'Portaria MEC')]

    polo = models.ForeignKeyPlus('edu.Polo', verbose_name='Polo', null=False, blank=False, on_delete=models.CASCADE)
    tipo_documento = models.CharFieldPlus(verbose_name='Tipo de Documento', choices=TIPO_DOCUMENTO_CHOICES)
    numero_documento = models.CharFieldPlus(verbose_name='Nº do Documento')
    data_publicacao = models.DateFieldPlus(verbose_name='Data da Publicação')
    arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='ato_regulatorio_polo', filetypes=['pdf'])

    class Meta:
        verbose_name = 'Ato Regulatório de Polo'
        verbose_name_plural = 'Atos Regulatórios de Polos'


class AtividadePolo(LogModel):
    polo = models.ForeignKeyPlus('edu.Polo', verbose_name='Polo', null=False, blank=False, on_delete=models.CASCADE)
    nome = models.CharFieldPlus('Nome')
    descricao = models.TextField('Descrição', null=True, blank=True)
    sala = models.ForeignKeyPlus('comum.Sala', null=True, blank=True)
    data_inicio = models.DateTimeFieldPlus('Data de Início', null=False, blank=False)
    data_fim = models.DateTimeFieldPlus('Data de Término', null=False, blank=False)
    user = models.CurrentUserField(verbose_name='Agendador')
    confirmada = models.BooleanField('Confirmada', default=False, null=False, blank=False)

    objects = models.Manager()
    locals = FiltroPoloManager('polo__diretoria', 'polo')

    class Meta:
        verbose_name = 'Atividade do Polo'
        verbose_name_plural = 'Atividades do Polo'

    def __str__(self):
        return self.nome

    def get_situacao(self, data=None):
        if not data:
            data = datetime.datetime.now()
        if data > self.data_inicio:
            if data < self.data_fim:
                return 'Acontecendo'
            else:
                return 'Vencido'
        else:
            return 'Novo'


class HorarioFuncionamentoPolo(LogModel):
    HORARIO_1 = 1
    HORARIO_2 = 2
    HORARIO_3 = 3
    HORARIO_4 = 4
    HORARIO_5 = 5
    HORARIO_6 = 6
    HORARIO_CHOICES = [[HORARIO_1, '1'], [HORARIO_2, '2'], [HORARIO_3, '3'], [HORARIO_4, '4'], [HORARIO_5, '5'], [HORARIO_6, '6']]
    polo = models.ForeignKeyPlus('edu.Polo', on_delete=models.CASCADE)
    numero = models.PositiveIntegerField(choices=HORARIO_CHOICES)
    turno = models.ForeignKeyPlus('edu.Turno', on_delete=models.CASCADE)
    inicio = models.CharFieldPlus('Início', max_length=5)
    termino = models.CharFieldPlus('Término', max_length=5)

    class Meta:
        verbose_name = 'Horário de Funcionamento'
        verbose_name_plural = 'Horários de Funcionamento'

    def __str__(self):
        return f'{self.inicio} - {self.termino}'

    def preencher_zeros(self, horario):
        if len(horario) < 5 and len(horario.split(':')) == 2:
            hora, minuto = horario.split(':')
            horario = f'{hora.zfill(2)}:{minuto.zfill(2)}'
        return horario

    def clean(self):
        self.inicio = self.preencher_zeros(self.inicio)
        self.termino = self.preencher_zeros(self.termino)

        try:
            parse(f'01/01/2012 {self.inicio}:00', dayfirst=True)
        except Exception:
            raise ValidationError(f'Hora de início inválida: {self.inicio}.')

        try:
            parse(f'01/01/2012 {self.termino}:00', dayfirst=True)
        except Exception:
            raise ValidationError(f'Hora de término inválida: {self.termino}.')


class TutorPolo(LogModel):
    SEARCH_FIELDS = ['vinculo__pessoa__nome', 'vinculo__user__username']

    polo = models.ForeignKeyPlus('edu.Polo', verbose_name='Polo', null=False, blank=False)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Tutor', null=False, blank=False)
    cursos = models.ManyToManyFieldPlus('edu.CursoCampus', verbose_name='Cursos', blank=False, related_name='tutor_set2')

    def __str__(self):
        return self.vinculo.pessoa.nome

    def get_horario(self):
        output = []
        horarios = HorarioTutorPolo.objects.filter(tutor=self, horario_funcionamento__polo=self.polo).order_by('dia_semana')
        turnos_ids = horarios.values_list('horario_funcionamento__turno', flat=True).distinct()
        for turno in Turno.objects.filter(id__in=turnos_ids):
            dias_semana = (
                self.horariotutorpolo_set.filter(horario_funcionamento__turno=turno)
                .order_by('dia_semana')
                .values_list('dia_semana', flat=True)
                .distinct()
            )
            for dia_semana in dias_semana:
                if output:
                    output.append(' / ')
                numeros = []
                for numero in (
                    self.horariotutorpolo_set.filter(horario_funcionamento__turno=turno, dia_semana=dia_semana)
                    .values_list('horario_funcionamento__numero', flat=True)
                    .distinct()
                ):
                    if numero not in numeros:
                        numeros.append(str(numero))
                numeros.sort()
                output.append('{}{}{}'.format(dia_semana + 1, turno.descricao[0], ''.join(numeros)))
        return ''.join(output)

    def get_horarios_por_turno(self, turno=None):
        if turno:
            turnos_ids = [turno.pk]
        else:
            turnos_ids = HorarioFuncionamentoPolo.objects.filter(polo=self.polo).values_list('turno__id', flat=True).distinct()

        dias_semana = HorarioTutorPolo.DIA_SEMANA_CHOICES
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')
        for turno in turnos:
            turno.horarios = []
            turno.dias_semana = dias_semana
            for horario in turno.horariofuncionamentopolo_set.filter(polo=self.polo):
                horario.dias_semana = []
                for dia_semana in dias_semana:
                    numero = dia_semana[0]
                    nome = dia_semana[1]
                    qs = self.horariotutorpolo_set.filter(dia_semana=dia_semana[0], horario_funcionamento=horario)
                    marcado = qs.count()
                    if qs.exists():
                        qs = qs[0]
                    else:
                        qs = None
                    horario.dias_semana.append({'numero': numero, 'nome': nome, 'marcado': marcado, 'horario_aula_diario': qs})
                turno.horarios.append(horario)
        return turnos

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if not self.vinculo.tutorpolo_set.exists():
            grupo = Group.objects.get(name='Tutor de Polo EAD')
            UsuarioGrupo.objects.filter(user=self.vinculo.user, group=grupo).delete()


class HorarioPolo(LogModel):
    DIA_SEMANA_SEG = 1
    DIA_SEMANA_TER = 2
    DIA_SEMANA_QUA = 3
    DIA_SEMANA_QUI = 4
    DIA_SEMANA_SEX = 5
    DIA_SEMANA_SAB = 6
    DIA_SEMANA_DOM = 7
    DIA_SEMANA_CHOICES = [
        [DIA_SEMANA_SEG, 'Segunda'],
        [DIA_SEMANA_TER, 'Terça'],
        [DIA_SEMANA_QUA, 'Quarta'],
        [DIA_SEMANA_QUI, 'Quinta'],
        [DIA_SEMANA_SEX, 'Sexta'],
        [DIA_SEMANA_SAB, 'Sábado'],
        [DIA_SEMANA_DOM, 'Domingo'],
    ]

    polo = models.ForeignKeyPlus('edu.Polo', on_delete=models.CASCADE)
    dia_semana = models.PositiveIntegerField(choices=DIA_SEMANA_CHOICES)
    horario_funcionamento = models.ForeignKeyPlus('edu.HorarioFuncionamentoPolo', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Horário do Polo'
        verbose_name_plural = 'Horários do Polo'

    def __str__(self):
        return str(self.pk)

    @staticmethod
    def get_dias_semana_seg_a_sex():
        dias_semana = []
        for dia in HorarioTutorPolo.DIA_SEMANA_CHOICES:
            if dia[0] < 6:
                dias_semana.append(dia)
        return dias_semana


class HorarioTutorPolo(LogModel):
    DIA_SEMANA_SEG = 1
    DIA_SEMANA_TER = 2
    DIA_SEMANA_QUA = 3
    DIA_SEMANA_QUI = 4
    DIA_SEMANA_SEX = 5
    DIA_SEMANA_SAB = 6
    DIA_SEMANA_DOM = 7
    DIA_SEMANA_CHOICES = [
        [DIA_SEMANA_SEG, 'Segunda'],
        [DIA_SEMANA_TER, 'Terça'],
        [DIA_SEMANA_QUA, 'Quarta'],
        [DIA_SEMANA_QUI, 'Quinta'],
        [DIA_SEMANA_SEX, 'Sexta'],
        [DIA_SEMANA_SAB, 'Sábado'],
        [DIA_SEMANA_DOM, 'Domingo'],
    ]

    tutor = models.ForeignKeyPlus('edu.TutorPolo', on_delete=models.CASCADE)
    dia_semana = models.PositiveIntegerField(choices=DIA_SEMANA_CHOICES)
    horario_funcionamento = models.ForeignKeyPlus('edu.HorarioFuncionamentoPolo', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Horário do Tutor'
        verbose_name_plural = 'Horários do Tutor'

    def __str__(self):
        return str(self.pk)

    @staticmethod
    def get_dias_semana_seg_a_sex():
        dias_semana = []
        for dia in HorarioTutorPolo.DIA_SEMANA_CHOICES:
            if dia[0] < 6:
                dias_semana.append(dia)
        return dias_semana


class CoordenadorPolo(LogModel):
    polo = models.ForeignKeyPlus('edu.Polo', verbose_name='Polo', null=False, blank=False)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Coordenador', null=False, blank=False)
    portaria_designacao = models.FileFieldPlus(
        verbose_name='Portaria de Designação', upload_to='portaria_coordenador_polo', filetypes=['pdf'], null=True, blank=True
    )
    titular = models.BooleanField('Titular', default=False)

    class Meta:
        verbose_name = 'Coordenador de Polo'
        verbose_name_plural = 'Coordenadores de Polo'

    def __str__(self):
        return self.vinculo.pessoa.nome

    def get_horario(self):
        output = []
        horarios = HorarioCoordenadorPolo.objects.filter(coordenador=self, horario_funcionamento__polo=self.polo).order_by('dia_semana')
        turnos_ids = horarios.values_list('horario_funcionamento__turno', flat=True).distinct()
        for turno in Turno.objects.filter(id__in=turnos_ids):
            dias_semana = (
                self.horariocoordenadorpolo_set.filter(horario_funcionamento__turno=turno)
                .order_by('dia_semana')
                .values_list('dia_semana', flat=True)
                .distinct()
            )
            for dia_semana in dias_semana:
                if output:
                    output.append(' / ')
                numeros = []
                for numero in (
                    self.horariocoordenadorpolo_set.filter(horario_funcionamento__turno=turno, dia_semana=dia_semana)
                    .values_list('horario_funcionamento__numero', flat=True)
                    .distinct()
                ):
                    if numero not in numeros:
                        numeros.append(str(numero))
                numeros.sort()
                output.append('{}{}{}'.format(dia_semana + 1, turno.descricao[0], ''.join(numeros)))
        return ''.join(output)

    def get_horarios_por_turno(self, turno=None):
        if turno:
            turnos_ids = [turno.pk]
        else:
            turnos_ids = HorarioFuncionamentoPolo.objects.filter(polo=self.polo).values_list('turno__id', flat=True).distinct()

        dias_semana = HorarioCoordenadorPolo.DIA_SEMANA_CHOICES
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')

        for turno in turnos:
            turno.horarios = []
            turno.dias_semana = dias_semana
            for horario in turno.horariofuncionamentopolo_set.filter(polo=self.polo):
                horario.dias_semana = []
                for dia_semana in dias_semana:
                    numero = dia_semana[0]
                    nome = dia_semana[1]
                    qs = self.horariocoordenadorpolo_set.filter(dia_semana=dia_semana[0], horario_funcionamento=horario)
                    marcado = qs.count()
                    if qs.exists():
                        qs = qs[0]
                    else:
                        qs = None
                    horario.dias_semana.append({'numero': numero, 'nome': nome, 'marcado': marcado, 'horario_aula_diario': qs})
                turno.horarios.append(horario)
        return turnos

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if not self.vinculo.coordenadorpolo_set.exists():
            grupo = Group.objects.get(name='Coordenador de Polo EAD')
            UsuarioGrupo.objects.filter(user=self.vinculo.user, group=grupo).delete()


class HorarioCoordenadorPolo(LogModel):
    DIA_SEMANA_SEG = 1
    DIA_SEMANA_TER = 2
    DIA_SEMANA_QUA = 3
    DIA_SEMANA_QUI = 4
    DIA_SEMANA_SEX = 5
    DIA_SEMANA_SAB = 6
    DIA_SEMANA_DOM = 7
    DIA_SEMANA_CHOICES = [
        [DIA_SEMANA_SEG, 'Segunda'],
        [DIA_SEMANA_TER, 'Terça'],
        [DIA_SEMANA_QUA, 'Quarta'],
        [DIA_SEMANA_QUI, 'Quinta'],
        [DIA_SEMANA_SEX, 'Sexta'],
        [DIA_SEMANA_SAB, 'Sábado'],
        [DIA_SEMANA_DOM, 'Domingo'],
    ]

    coordenador = models.ForeignKeyPlus('edu.CoordenadorPolo', on_delete=models.CASCADE)
    dia_semana = models.PositiveIntegerField(choices=DIA_SEMANA_CHOICES)
    horario_funcionamento = models.ForeignKeyPlus('edu.HorarioFuncionamentoPolo', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Horário do Coordenador do Polo'
        verbose_name_plural = 'Horários do Coordenador do Polo'

    def __str__(self):
        return str(self.pk)

    @staticmethod
    def get_dias_semana_seg_a_sex():
        dias_semana = []
        for dia in HorarioCoordenadorPolo.DIA_SEMANA_CHOICES:
            if dia[0] < 6:
                dias_semana.append(dia)
        return dias_semana
