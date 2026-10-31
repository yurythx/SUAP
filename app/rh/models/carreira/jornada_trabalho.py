import re

from djtools.db import models

_NOME_JORNADA_SEMANAL = re.compile(r'^(\d+(?:,\d+)?) HORAS SEMANAIS$')


class JornadaTrabalho(models.ModelPlus):
    codigo = models.CharField(max_length=10, null=True, unique=True)  # "40"
    nome = models.CharField(max_length=40)  # "40 horas semanais"
    excluido = models.BooleanField(default=False)
    docente_peso = models.FloatField(default=1)

    _CACHE = []

    @classmethod
    def get_jornada(cls, nome):
        if not cls._CACHE:
            cls._CACHE = list(cls.objects.all())
        for jornada in cls._CACHE:
            if jornada.nome == nome:
                return jornada
        return None

    def __str__(self):
        return self.nome

    def get_jornada_trabalho_diaria(self) -> int | float | None:
        """Horas por dia (semanal / 5): int quando exato (40 → 8), float senão (32,5 → 6.5); None se o nome não traz horas."""
        semanal = self.get_jornada_trabalho_semanal()
        if semanal is None:
            return None
        return semanal // 5 if semanal % 5 == 0 else semanal / 5

    def get_jornada_trabalho_semanal(self) -> int | float | None:
        """Horas por semana lidas do nome ('N HORAS SEMANAIS', N com vírgula decimal opcional); DEDICACAO EXCLUSIVA = 40."""
        if self.nome == 'DEDICACAO EXCLUSIVA':
            return 40
        correspondencia = _NOME_JORNADA_SEMANAL.match(self.nome or '')
        if not correspondencia:
            return None
        horas = float(correspondencia.group(1).replace(',', '.'))
        return int(horas) if horas.is_integer() else horas

    def get_jornada_trabalho_semanal_abreviada(self):
        if self.nome == 'DEDICACAO EXCLUSIVA':
            return 'DE'
        else:
            horas = self.get_jornada_trabalho_semanal()
            return f'{horas}h' if horas else None

    @staticmethod
    def situacoes_usadas_no_instituto():
        from ..carreira import Servidor

        jornadas_servidores = (
            Servidor.objects.filter(jornada_trabalho__isnull=False).values_list('jornada_trabalho', flat=True).order_by('jornada_trabalho').distinct()
        )
        return JornadaTrabalho.objects.filter(id__in=jornadas_servidores)

    class Meta:
        db_table = 'jornada_trabalho'
        verbose_name = 'Jornada de Trabalho'
        verbose_name_plural = 'Jornadas de Trabalho'


class JornadaTrabalhoPersonalizada:
    """Jornada de trabalho diária e semanal, não persistente, usada para permitir CHs quaisquer, superando
    a limitação do modelo JornadaTrabalho que permite apenas CHs predefinidas semanais de 40, 30, 25 e 20, com
    a dedução da CH diária.

    É possível instanciar esta classe e usá-la no código como se fosse uma instãncia de
    JornadaTrabalho nas situações onde deve "chegar" uma CH diária ou semanal personalizada (ex: CH Reduzida no ponto)
    """

    ch_dia: float = None
    ch_semana: float = None

    """
        Usos:

        Com foco na CH de um dia específico:
            1-informa quaisquer CH do dia (ch_dia)
            2-informa quaisquer CH da semana do dia em questão (ch_semana) ou não informa nenhuma CH da semana (ch_semana será deduzida)

        Com foco na CH de uma semana específica:
            1-não informa nenhuma CH do dia (ch_dia será deduzida)
            2-informa quaisquer CH da semana (ch_semana)
    """

    def __init__(self, ch_dia: float | None = None, ch_semana: float | None = None):
        self.ch_dia = ch_dia
        self.ch_semana = ch_semana

    @property
    def nome(self) -> str:
        jornada_semanal = self.get_jornada_trabalho_semanal()
        if jornada_semanal > 0:
            ch_h = int(jornada_semanal)
            ch_min = round(60 * (jornada_semanal - float(ch_h)))
            if ch_min < 10:
                ch_min = f'0{ch_min}'
            return f'{ch_h}:{ch_min} SEMANAIS'
        return '00:00 SEMANAIS'

    def __str__(self):
        return self.nome

    def get_jornada_trabalho_diaria(self) -> float:
        # ch_dia = 0 é diferente de ch_dia = None
        return self.ch_dia if self.ch_dia is not None else (self.ch_semana or 0.0) / 5

    def get_jornada_trabalho_semanal(self) -> float:
        # ch_semana = 0 é diferente de ch_semana = None
        return self.ch_semana if self.ch_semana is not None else (self.ch_dia or 0.0) * 5
