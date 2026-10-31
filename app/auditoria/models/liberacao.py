from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q
from django.db.models.functions import Coalesce, ExtractDay, ExtractMonth

from djtools.db import models
from djtools.utils import get_datetime_now, is_final_de_semana
from rh.models import UnidadeOrganizacional


class CategoriaLiberacao(models.IntegerChoices):
    FERIADO = 1, 'Feriado'  # pontual: usa data_início/data_fim (um dia ou intervalo)
    FERIADO_RECORRENTE = 2, 'Feriado recorrente'  # fixo anual: usa mês/dia
    RECESSO = 3, 'Recesso'  # pontual: usa data_início/data_fim (normalmente intervalo)


class TipoExpediente(models.IntegerChoices):
    LIBERADO = 1, 'Liberado'  # Sem trabalho
    MEIO_EXPEDIENTE = 2, 'Meio expediente'  # Até 14h


class LiberacaoProgramadaQuerySet(models.QuerySet):
    def ativas(self):
        return self.filter(ativo=True)

    def desconto_total_periodo(self, jornada_diaria_horas: float, inicio: date, fim: date) -> float:
        if inicio > fim:
            return 0.0

        liberacoes = list(self.filter())
        total = 0.0
        atual = inicio
        um_dia = timedelta(days=1)

        while atual <= fim:
            # aplica o MAIOR desconto do dia dentre as liberações (evita somar em dobro)
            max_desc = 0.0
            for liberacao in liberacoes:
                desconto = liberacao.desconto_no_dia(atual, jornada_diaria_horas)
                if desconto > max_desc:
                    max_desc = desconto
                    if max_desc >= float(jornada_diaria_horas):
                        break
            total += min(max_desc, jornada_diaria_horas)
            atual += um_dia
        return total


class LiberacaoProgramadaManager(models.Manager):
    def get_queryset(self):
        return LiberacaoProgramadaQuerySet(self.model, using=self._db)

    def ativas(self):
        return self.get_queryset().ativas()

    def desconto_total_periodo(self, jornada_diaria_horas: float, inicio: date, fim: date) -> float:
        return self.get_queryset().desconto_total_periodo(jornada_diaria_horas, inicio, fim)


class LiberacaoProgramada(models.ModelPlus):
    nome = models.CharField(max_length=120)
    descricao = models.TextField(blank=True)
    categoria = models.PositiveSmallIntegerField(
        choices=CategoriaLiberacao.choices,
        default=CategoriaLiberacao.FERIADO,
    )
    uo = models.ForeignKey(
        UnidadeOrganizacional,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name='Unidade Organizacional',
        help_text='Se vazio, aplica globalmente; caso contrário, ao município da UO.',
        related_name='liberacoes',
    )

    tipo_expediente = models.PositiveSmallIntegerField(
        choices=TipoExpediente.choices,
        default=TipoExpediente.LIBERADO,
        help_text='Define a exigência de horas no(s) dia(s) da liberação.',
    )
    data_inicio = models.DateField(blank=True, null=True)
    data_fim = models.DateField(blank=True, null=True)

    mes_recorrente = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    dia_recorrente = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )

    ativo = models.BooleanField(default=True)

    objects = LiberacaoProgramadaManager()

    class Meta:
        verbose_name = 'Liberação Programada'
        verbose_name_plural = 'Liberações Programadas'
        constraints = [
            # Evita duplicar recorrente (mes/dia) no mesmo escopo
            models.UniqueConstraint(
                fields=['uo', 'categoria', 'mes_recorrente', 'dia_recorrente'],
                name='uniq_liberacao_recorrente_uo_mes_dia',
                condition=models.Q(categoria=CategoriaLiberacao.FERIADO_RECORRENTE),
            ),
            # Evita duplicar pontual (intervalo) no mesmo escopo
            models.UniqueConstraint(
                fields=['uo', 'categoria', 'data_inicio', 'data_fim'],
                name='uniq_liberacao_pontual_uo_intervalo',
                condition=models.Q(categoria__in=[CategoriaLiberacao.FERIADO, CategoriaLiberacao.RECESSO]),
            ),
        ]

    def __str__(self):
        return f'{self.nome} ({self.get_categoria_display()})'

    @property
    def eh_recorrente(self) -> bool:
        return self.categoria == CategoriaLiberacao.FERIADO_RECORRENTE

    def carga_horaria(self, jornada_diaria: float = 8.0) -> float:
        """Retorna quantas horas são EXIGIDAS no dia da liberação."""
        if self.tipo_expediente == TipoExpediente.LIBERADO:
            return 0.0
        # Meio expediente = 50% da jornada
        if self.tipo_expediente == TipoExpediente.MEIO_EXPEDIENTE:
            return max(jornada_diaria / 2.0, 0.0)
        return jornada_diaria

    def _periodo_default(self) -> tuple[date, date] | None:
        """
        Se for recorrente -> um dia no ano atual (ou no ano que você passar).
        Se for pontual -> (data_inicio, data_fim or data_inicio).
        """
        if self.eh_recorrente:
            # por padrão, usa o ano corrente
            hoje = get_datetime_now().date()
            try:
                data = date(hoje.year, self.mes_recorrente, self.dia_recorrente)
            except Exception:
                return None
            return (data, data)
        if not self.data_inicio:
            return None
        return (self.data_inicio, self.data_fim or self.data_inicio)

    def desconto_no_dia(self, dia: date, jornada_diaria_horas: float) -> float:
        """Quanto deve ser DESCONTADO (em horas) neste dia."""
        if not self.ativo or is_final_de_semana(dia):
            return 0.0

        # Checa ocorrência da liberação naquele dia
        if self.eh_recorrente:
            if self.mes_recorrente == dia.month and self.dia_recorrente == dia.day:
                # desconto = horas previstas do dia - horas exigidas
                return jornada_diaria_horas - self.carga_horaria(jornada_diaria_horas)
            return 0.0

        # Pontual
        ini = self.data_inicio
        fim = self.data_fim or ini
        if ini <= dia <= fim:
            return jornada_diaria_horas - self.carga_horaria(jornada_diaria_horas)
        return 0.0

    def desconto_no_periodo(self, inicio: date, fim: date, jornada_diaria_horas: float) -> float:
        """Soma de desconto (em horas) no intervalo [inicio, fim]."""
        current = inicio
        total = 0.0
        one_day = timedelta(days=1)
        while current <= fim:
            total += self.desconto_no_dia(current, jornada_diaria_horas)
            current += one_day
        return total

    def desconto_total(self, jornada_diaria_horas: float, inicio: date | None = None, fim: date | None = None) -> float:
        """
        Desconto total (em horas) desta liberação no intervalo informado.
        Se não informar intervalo, usa o período default da própria liberação.
        """
        if not inicio or not fim:
            periodo = self._periodo_default()
            if not periodo:
                return 0.0
            inicio, fim = periodo
        # Calcula desconto no período
        return self.desconto_no_periodo(inicio, fim, jornada_diaria_horas)

    def ocorre_em(self, ano: int) -> list[tuple[date, date]]:
        """
        Lista de intervalos (inicio, fim) dentro do ano informado:
        - recorrente: 1 dia
        - pontual: intervalo recortado ao ano (admite atravessar anos)
        """
        if not self.ativo:
            return []

        if self.eh_recorrente:
            try:
                data = date(ano, self.mes_recorrente, self.dia_recorrente)
            except Exception:
                return []
            return [(data, data)]

        inicio = self.data_inicio
        fim = self.data_fim or self.data_inicio
        if fim.year < ano or inicio.year > ano:
            return []
        inicio_recorrencia = date(ano, 1, 1) if inicio.year < ano else inicio
        fim_recorrencia = date(ano, 12, 31) if fim.year > ano else fim
        return [(inicio_recorrencia, fim_recorrencia)]

    def verificar_liberacao_duplicada(self):
        from ponto.models import Liberacao, TipoLiberacao

        if self.categoria in (CategoriaLiberacao.FERIADO, CategoriaLiberacao.RECESSO):
            if not self.data_inicio:
                raise ValidationError({'data_inicio': 'Informe a data de início.'})
            if self.data_fim and self.data_fim < self.data_inicio:
                raise ValidationError({'data_fim': 'Data fim não pode ser anterior à data início.'})
            if self.mes_recorrente or self.dia_recorrente:
                raise ValidationError('Pontuais não podem ter recorrência.')
        elif self.categoria == CategoriaLiberacao.FERIADO_RECORRENTE:
            if not (self.mes_recorrente and self.dia_recorrente):
                raise ValidationError('Recorrentes exigem mês e dia.')
            if self.data_inicio or self.data_fim:
                raise ValidationError('Recorrentes não podem ter datas.')
        # --- validações contra Liberacao (Ponto) ---
        base_qs = Liberacao.objects.filter(Q(uo=self.uo) | Q(uo__isnull=True))
        tipo_feriado = TipoLiberacao.get_numero(TipoLiberacao.FERIADO)
        tipo_recesso = TipoLiberacao.get_numero(TipoLiberacao.RECESSO)
        tipo_recorrente = TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE)

        if self.categoria == CategoriaLiberacao.FERIADO_RECORRENTE:
            qs = base_qs.filter(tipo=tipo_recorrente).annotate(mes=ExtractMonth('data_inicio'), dia=ExtractDay('data_inicio'))
            existe_colisao = qs.filter(mes=self.mes_recorrente, dia=self.dia_recorrente).exists()
            if existe_colisao:
                raise ValidationError('Já existe liberação recorrente no Ponto para esta data.')
        else:
            ini = self.data_inicio
            fim = self.data_fim or ini
            # sobreposição com feriados/recessos
            qs = base_qs.filter(tipo__in=[tipo_feriado, tipo_recesso]).annotate(fim_norm=Coalesce('data_fim', 'data_inicio'))
            existe_colisao = qs.filter(Q(data_inicio__lte=fim) & Q(fim_norm__gte=ini)).exists()
            if existe_colisao:
                raise ValidationError('Já existe liberação no Ponto que cobre esse intervalo.')
            # colisão com recorrentes
            recorrentes_qs = base_qs.filter(tipo=tipo_recorrente).annotate(mes=ExtractMonth('data_inicio'), dia=ExtractDay('data_inicio'))
            recorrentes = recorrentes_qs.values('mes', 'dia')
            recorrentes_set = {(recorrente['mes'], recorrente['dia']) for recorrente in recorrentes}
            cur = ini
            while cur <= fim:
                if (cur.month, cur.day) in recorrentes_set:
                    raise ValidationError('Já existe liberação recorrente no Ponto nesse intervalo.')
                cur += timedelta(days=1)

    def clean(self):
        if not self.ativo:
            return

        tem_datas = bool(self.data_inicio)  # data_fim é opcional
        tem_recorrencia = bool(self.mes_recorrente and self.dia_recorrente)

        if self.categoria == CategoriaLiberacao.FERIADO_RECORRENTE:
            if not tem_recorrencia:
                raise ValidationError('Feriado recorrente requer mês e dia.')

            if tem_datas:
                raise ValidationError('Feriado recorrente não deve definir data_inicio/data_fim.')
            # limpa datas
            self.data_inicio = None
            self.data_fim = None
        elif self.categoria in (CategoriaLiberacao.FERIADO, CategoriaLiberacao.RECESSO):
            if not tem_datas:
                raise ValidationError('Feriado/Recesso requer pelo menos data_inicio.')

            if self.data_fim and self.data_fim < self.data_inicio:
                raise ValidationError('data_fim não pode ser anterior a data_inicio.')

            if tem_recorrencia:
                raise ValidationError('Feriado/Recesso pontual não deve definir mês/dia recorrentes.')
            # limpa recorrência
            self.mes_recorrente = None
            self.dia_recorrente = None

    def save(self, *args, validate=True, **kwargs):
        if validate:
            self.full_clean()
            self.verificar_liberacao_duplicada()
        return super().save(*args, **kwargs)
