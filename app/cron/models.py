import os
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime

from django.conf import settings
from django.core.management import get_commands
from django.db.models import signals

from djtools.db import models
from djtools.db.models import ModelPlus


class Comando(ModelPlus):
    nome = models.CharFieldPlus(max_length=80, unique=True)

    def __str__(self):
        return self.nome

    @classmethod
    def create_commands_from_django(cls):
        for command, app in list(get_commands().items()):
            if app in settings.INSTALLED_APPS_SUAP:
                cls.objects.get_or_create(nome=command)

    class Meta:
        verbose_name_plural = 'Comandos de sistema'
        verbose_name = 'Comando de sistema'
        ordering = ('nome',)


class ComandoAgendamento(ModelPlus):
    comando = models.ForeignKeyPlus(Comando)
    parametros = models.CharFieldPlus(null=True, blank=True)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.comando} {self.get_parametros()}'

    def get_parametros(self):
        if self.parametros is None:
            return ''
        return self.parametros

    def executar(self, user=None):
        if self.ativo:
            registro = LogExecucao.objects.create(comando=self)
            try:
                p = subprocess.Popen(
                    f'{sys.executable} {settings.BASE_DIR}/manage.py {self.comando.nome} {self.get_parametros()}',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    shell=True,
                )
                registro.log = ''
                registro.usuario = user
                for line in iter(p.stdout.readline, b''):
                    registro.log += line.decode()
                    registro.save()
                p.stdout.close()
                p.wait()
                registro.fim = datetime.now()
                registro.status = True
            except Exception:
                tb = traceback.format_exc()
                registro.fim = datetime.now()
                registro.traceback = tb
            finally:
                registro.save()

    class Meta:
        verbose_name_plural = 'Comandos para agendamento'
        verbose_name = 'Comando para agendamento'
        ordering = ('comando__nome',)


class LogExecucao(ModelPlus):
    comando = models.ForeignKeyPlus(ComandoAgendamento, verbose_name='Comando')
    inicio = models.DateTimeFieldPlus(verbose_name='Início', auto_now_add=True)
    fim = models.DateTimeFieldPlus(verbose_name='Fim', null=True)
    status = models.BooleanField(default=False)
    traceback = models.TextField(verbose_name='Traceback')
    log = models.TextField(verbose_name='Log', null=True, blank=True)
    usuario = models.ForeignKeyPlus(settings.AUTH_USER_MODEL, verbose_name='Usuário', null=True, blank=True)

    def __str__(self):
        return str(self.comando)

    class Meta:
        verbose_name_plural = 'Logs de execução'
        verbose_name = 'Log de execução'

    def interromper(self):
        self.fim = datetime.now()
        self.save()


MINUTOS = tuple([(str(x), str(x)) for x in range(60)])
HORAS = tuple([('*', 'Todas')] + [(str(x), str(x)) for x in range(24)])
DIAS_DO_MES = tuple([('*', 'Todos')] + [(str(x), str(x)) for x in range(1, 32)])
MES = tuple([('*', 'Todos')] + [(str(x), str(x)) for x in range(1, 13)])
DIAS_DA_SEMANA = (
    ('*', 'Todos'),
    ('1', 'Segunda-feira'),
    ('2', 'Terça-feira'),
    ('3', 'Quarta-feira'),
    ('4', 'Quinta-feira'),
    ('5', 'Sexta-feira'),
    ('6', 'Sábado'),
    ('7', 'Domingo'),
)


class Agendamento(ModelPlus):
    nome = models.CharFieldPlus(unique=True)
    minuto = models.CharFieldPlus(max_length=4, choices=MINUTOS, blank=False, default='0')
    hora = models.CharFieldPlus(max_length=4, choices=HORAS, blank=False, default='0')
    dia_do_mes = models.CharFieldPlus(max_length=4, verbose_name='Dia do mês', choices=DIAS_DO_MES, blank=False, default='*')
    mes = models.CharFieldPlus(max_length=4, verbose_name='Mês', choices=MES, blank=False, default='*')
    dia_da_semana = models.CharFieldPlus(max_length=4, verbose_name='Dia da semana', choices=DIAS_DA_SEMANA, blank=False, default='*')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    ativo = models.BooleanField(default=True)
    comandos = models.ManyToManyField(ComandoAgendamento)

    def __str__(self):
        return self.nome

    def get_cron_line(self):
        return f'{self.minuto} {self.hora} {self.dia_do_mes} {self.mes} {self.dia_da_semana} {self.get_comando_suap()} agendamento {self.id}'

    def get_comando_suap(self):
        executable = sys.executable
        path = os.path.join(os.path.dirname(__file__), '..')
        return f'{executable} {path}/manage.py'

    class Meta:
        verbose_name_plural = 'Agendamentos'
        verbose_name = 'Agendamento'

    def get_comandos_ativos(self):
        return self.comandos.filter(ativo=True)

    def executar(self):
        if self.ativo:
            for comando in self.get_comandos_ativos():
                comando.executar()


class MensalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(mes='*', dia_da_semana='*').exclude(dia_do_mes='*')


class AgendamentoMensal(Agendamento):
    class Meta:
        proxy = True
        verbose_name_plural = 'Agendamentos mensais'
        verbose_name = 'Agendamento mensal'

    objects = MensalManager()


class DiarioManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(dia_do_mes='*', mes='*', dia_da_semana='*')


class AgendamentoDiario(Agendamento):
    class Meta:
        proxy = True
        verbose_name_plural = 'Agendamentos diários'
        verbose_name = 'Agendamento diário'

    objects = DiarioManager()


class SemanalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(dia_do_mes='*', mes='*').exclude(dia_da_semana='*')


class AgendamentoSemanal(Agendamento):
    class Meta:
        proxy = True
        verbose_name_plural = 'Agendamentos semanais'
        verbose_name = 'Agendamento semanal'

    objects = SemanalManager()


class HoraEmHoraManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(dia_do_mes='*', mes='*', dia_da_semana='*', hora='*')


class AgendamentoHoraEmHora(Agendamento):
    class Meta:
        proxy = True
        verbose_name_plural = 'Agendamentos de hora em hora'
        verbose_name = 'Agendamento hora em hora'

    objects = HoraEmHoraManager()


def atualizar_cron(sender, instance, signal, **kwargs):
    with tempfile.NamedTemporaryFile(mode='w') as f:
        arquivo = f.name
        p = subprocess.Popen('crontab -l', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        for line in iter(p.stdout.readline, b''):
            try:
                if 'agendamento' not in line:
                    f.write(line)
            except TypeError:
                if 'agendamento' not in line.decode():
                    f.write(line.decode())
        f.writelines(str(agendamento.get_cron_line()) + '\n' for agendamento in Agendamento.objects.filter(ativo=True))

        subprocess.check_call(['crontab', arquivo])


signals.post_save.connect(atualizar_cron, sender=Agendamento)
signals.post_save.connect(atualizar_cron, sender=AgendamentoSemanal)
signals.post_save.connect(atualizar_cron, sender=AgendamentoDiario)
signals.post_save.connect(atualizar_cron, sender=AgendamentoHoraEmHora)
signals.post_save.connect(atualizar_cron, sender=AgendamentoMensal)
signals.post_delete.connect(atualizar_cron, sender=Agendamento)
signals.post_delete.connect(atualizar_cron, sender=AgendamentoSemanal)
signals.post_delete.connect(atualizar_cron, sender=AgendamentoDiario)
signals.post_delete.connect(atualizar_cron, sender=AgendamentoHoraEmHora)
signals.post_delete.connect(atualizar_cron, sender=AgendamentoMensal)
