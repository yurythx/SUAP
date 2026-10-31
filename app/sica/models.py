import math

from django.apps.registry import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from comum.models import RegistroEmissaoDocumento
from djtools.db import models
from edu.models import Aluno


class Matriz(models.ModelPlus):
    nome = models.CharFieldPlus(verbose_name='Nome')
    codigo = models.CharFieldPlus(verbose_name='Código', null=True, blank=True)
    carga_horaria = models.CharFieldPlus(verbose_name='Carga-Horária Obrigatória', null=True, blank=True)
    carga_horaria_estagio = models.CharFieldPlus(verbose_name='Carga-Horária de Estágio', null=True, blank=True)
    reconhecimento = models.TextField(verbose_name='Reconhecimento', null=True, blank=True)

    class Meta:
        verbose_name = 'Matriz'
        verbose_name_plural = 'Matrizes'

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/sica/matriz/{self.pk}/'

    def get_nome_simplicado_curso(self):
        return self.nome.split()[-1]

    def get_componentes_curriculares(self, ano_inicio=None, ano_fim=None):
        qs = self.componentecurricular_set.all().order_by('periodo', 'pk')
        if ano_inicio:
            qs = qs.exclude(ate__isnull=False, ate__lt=ano_inicio)
        if ano_fim:
            qs = qs.exclude(desde__isnull=False, desde__gt=ano_fim)
        return qs

    def atualizar_carga_horaria_total(self):
        self.carga_horaria = 0
        for componente_curricular in self.componentecurricular_set.filter(opcional=False):
            self.carga_horaria += componente_curricular.carga_horaria or 0
        self.save()


class Componente(models.ModelPlus):
    codigo = models.CharFieldPlus(verbose_name='Código')
    nome = models.CharFieldPlus(verbose_name='Nome', null=True)
    sigla = models.CharFieldPlus(verbose_name='Sigla', null=True)

    class Meta:
        verbose_name = 'Componente'
        verbose_name_plural = 'Componentes'

    def __str__(self):
        return self.nome or ''


class ComponenteCurricular(models.ModelPlus):
    FORMACAO_GERAL = 'Formação Geral'
    FORMACAO_ESPECIFICA = 'Formação Específica'

    matriz = models.ForeignKeyPlus(Matriz, verbose_name='Matriz', on_delete=models.CASCADE)
    componente = models.ForeignKeyPlus(Componente, verbose_name='Componente', on_delete=models.CASCADE)
    periodo = models.IntegerField(verbose_name='Período', choices=[[x, x] for x in range(1, 8)])
    qtd_creditos = models.IntegerField(verbose_name='Qtd. Aulas Semanais', null=True, blank=True)
    carga_horaria = models.IntegerField(verbose_name='C.H.', null=True, blank=True)
    tipo = models.CharFieldPlus(
        verbose_name='Tipo', default=FORMACAO_GERAL, choices=[(FORMACAO_GERAL, FORMACAO_GERAL), (FORMACAO_ESPECIFICA, FORMACAO_ESPECIFICA)]
    )
    opcional = models.BooleanField(verbose_name='Opcional', default=False, blank=True)
    equivalencias = models.ManyToManyFieldPlus('sica.ComponenteCurricular', verbose_name='Equivalências', blank=True)

    desde = models.IntegerField(verbose_name='A partir de', null=True, blank=True)
    ate = models.IntegerField(verbose_name='Até', null=True, blank=True)

    class Meta:
        verbose_name = 'Componente'
        verbose_name_plural = 'Componentes'

    def __str__(self):
        return f'{self.componente} - {self.periodo}º Nível'

    def save(self, *args, **kwargs):
        if self.qtd_creditos:
            self.carga_horaria = self.qtd_creditos * 15
        super().save(*args, **kwargs)
        self.matriz.atualizar_carga_horaria_total()


class Historico(models.ModelPlus):
    aluno = models.ForeignKeyPlus(Aluno, verbose_name='Aluno', on_delete=models.CASCADE)
    matriz = models.ForeignKeyPlus(Matriz, verbose_name='Matriz', null=True, on_delete=models.CASCADE)
    comprovou_experiencia_proficional = models.BooleanField(
        verbose_name='Comprovou Experiência Profisional',
        default=False,
        help_text='Marque essa opção caso o aluno tenha recorrido à portal 426/94 - DG/ETFRN',
    )
    carga_horaria_estagio = models.IntegerField(verbose_name='C.H. de Estágio', null=True, blank=True)

    componentes_curriculares = models.ManyToManyField(ComponenteCurricular, verbose_name='Componentes Curriculares')

    ultima_via_emitida = models.IntegerField(verbose_name='Última Via Emitida', null=True, blank=True, default=1)

    class Meta:
        verbose_name = 'Histórico'
        verbose_name_plural = 'Históricos'

    def __str__(self):
        return self.aluno.pessoa_fisica.nome

    def clean(self):
        if self.id is None and Historico.objects.filter(aluno_id=self.aluno_id).exists():
            raise ValidationError('Este aluno já possui um lançamento de histórico.')

    def get_absolute_url(self):
        return f'/sica/historico/{self.pk}/'

    def tem_registro_emissao_documento(self):
        tipo_modelo = ContentType.objects.get_for_model(apps.get_model('sica.Historico'))
        return RegistroEmissaoDocumento.objects.filter(
            tipo__in=['Histórico SICA', 'Declaração SICA'], tipo_objeto=tipo_modelo, modelo_pk=self.pk
        ).exists()

    def excluir_registros_emissao_documento(self):
        tipo_modelo = ContentType.objects.get_for_model(apps.get_model('sica.Historico'))
        RegistroEmissaoDocumento.objects.filter(tipo__in=['Histórico SICA', 'Declaração SICA'], tipo_objeto=tipo_modelo, modelo_pk=self.pk).delete()

    def get_registros(self):
        return (
            ('Curriculares', self.get_registros_curriculares()),
            # ('Extracurriculares', self.get_registros_extra_curriculares()),
        )

    def get_ch_cumprida(self):
        ch = 0
        for registro in self.registrohistorico_set.all():
            carga_horaria = registro.get_carga_horaria()
            if carga_horaria is not None and carga_horaria.isdigit():
                ch += int(carga_horaria)
        return ch

    def get_ch_geral(self):
        lista = []
        for registro in self.registrohistorico_set.filter(tipo=ComponenteCurricular.FORMACAO_GERAL):
            carga_horaria = registro.get_carga_horaria()
            if carga_horaria and carga_horaria.isdigit():
                lista.append(int(carga_horaria))
        return sum(lista)

    def get_ch_especial(self):
        lista = []
        for registro in self.registrohistorico_set.filter(tipo=ComponenteCurricular.FORMACAO_ESPECIFICA):
            carga_horaria = registro.get_carga_horaria()
            if carga_horaria and carga_horaria.isdigit():
                lista.append(int(carga_horaria))
        return sum(lista)

    def get_ultimo_periodo_letivo(self):
        registro = self.registrohistorico_set.order_by('-ano', '-periodo').exclude(periodo_matriz__gt=6).first()
        if registro is None:
            raise ValueError('Nenhum registro histórico encontrado.')
        return registro.ano, registro.periodo

    def get_registros_curriculares(self):
        return self.registrohistorico_set.all().order_by('periodo_matriz', 'componente__codigo')

    def get_registros_extra_curriculares(self):
        return self.registrohistorico_set.exclude(componente__in=self.componentes_curriculares.values_list('componente', flat=True)).order_by(
            'periodo_matriz', 'componente__codigo'
        )

    def get_nivel_em(self, ano):
        registro = self.registrohistorico_set.filter(periodo_matriz__isnull=False, ano=ano).first()
        return registro and registro.periodo_matriz or None

    def organizar_historico(self):
        if not self.componentes_curriculares.exists():
            pagou_dependencia = False
            for componente in Componente.objects.filter(pk__in=self.matriz.componentecurricular_set.values_list('componente', flat=True)):
                periodos = list(
                    self.matriz.componentecurricular_set.filter(componente=componente).order_by('-periodo').values_list('periodo', flat=True)
                )
                for registro in self.registrohistorico_set.filter(ano__isnull=False, periodo__isnull=False, componente=componente).order_by(
                    'ano', 'periodo', 'nota'
                ):
                    if periodos:
                        periodo_matriz = periodos.pop()
                        registro.periodo_matriz = periodo_matriz
                        registro.save()
            for componente_curricular in self.matriz.componentecurricular_set.all():
                pode_adicionar = False
                # o componente foi ofertado em um determinado período
                if componente_curricular.desde or componente_curricular.ate:
                    pode_adicionar_desde = False
                    pode_adicionar_ate = False
                    nivel_desde = self.get_nivel_em(componente_curricular.desde)
                    if nivel_desde and nivel_desde <= componente_curricular.periodo:
                        pode_adicionar_desde = True
                    nivel_ate = self.get_nivel_em(componente_curricular.ate)
                    if nivel_ate and nivel_ate >= componente_curricular.periodo:
                        pode_adicionar_ate = True
                    # o período só possui data de início
                    if componente_curricular.desde and not componente_curricular.ate:
                        pode_adicionar = pode_adicionar_desde
                    # o período só possui data de término
                    elif componente_curricular.ate and not componente_curricular.desde:
                        pode_adicionar = pode_adicionar_ate
                    # o período possui data de início e término
                    else:
                        pode_adicionar = pode_adicionar_desde and pode_adicionar_ate
                else:
                    pode_adicionar = True

                if pode_adicionar:
                    qs = self.registrohistorico_set.filter(componente=componente_curricular.componente, periodo_matriz=componente_curricular.periodo)
                    if qs.exists():
                        if componente_curricular.opcional:
                            qs.update(opcional=True)
                    else:
                        # caso o aluno tenha cursado alguma disciplina equivalente
                        possui_equivante_cumprido = self.cursou_equivalente(componente_curricular)
                        # caso o aluno tenha ficado em dependência
                        if (
                            self.registrohistorico_set.filter(
                                componente=componente_curricular.componente, periodo_matriz=componente_curricular.periodo + 1, ano__isnull=False
                            ).count()
                            == 2
                        ):
                            pagou_dependencia = True
                        if not possui_equivante_cumprido and not pagou_dependencia:
                            RegistroHistorico.objects.create(
                                historico=self,
                                componente=componente_curricular.componente,
                                periodo_matriz=componente_curricular.periodo,
                                opcional=componente_curricular.opcional,
                            )
                    self.componentes_curriculares.add(componente_curricular)
            self.save()

    def concluiu_estagio(self):
        return self.carga_horaria_estagio and self.carga_horaria_estagio > 850 or False

    def get_ids_componentes_cursados(self):
        qs = self.registrohistorico_set.filter(ano__isnull=False, periodo__isnull=False).exclude(situacao__in=['M', 'X'])
        return qs.values_list('componente_id', flat=True)

    def get_periodo_realizacao(self):
        ano_inicio = self.aluno.ano_letivo.ano
        ano_fim = self.aluno.ano_letivo.ano
        qs = self.registrohistorico_set.filter(ano__isnull=False)
        if qs.exists():
            ano_inicio = qs.order_by('ano')[0].ano
            ano_fim = qs.order_by('-ano')[0].ano
        return ano_inicio, ano_fim

    def cursou_equivalente(self, componente_curricular):
        possui_equivante_cumprido = False
        for equivalencia in componente_curricular.equivalencias.all():
            if self.registrohistorico_set.filter(componente=equivalencia.componente, periodo_matriz=equivalencia.periodo, ano__isnull=False).exists():
                possui_equivante_cumprido = True
        return possui_equivante_cumprido

    def concluiu_sexto_periodo(self):
        qs = self.componentes_curriculares.filter(periodo__lt=6, opcional=False).exclude(componente__in=self.get_ids_componentes_cursados())
        pendentes = qs.count()
        for componente_curricular in qs:
            if self.cursou_equivalente(componente_curricular):
                pendentes = pendentes - 1
        return pendentes == 0

    def concluiu_todos_periodos(self):
        qs = self.componentes_curriculares.filter(opcional=False).exclude(componente__in=self.get_ids_componentes_cursados())
        pendentes = qs.count()
        for componente_curricular in qs:
            if self.cursou_equivalente(componente_curricular):
                pendentes = pendentes - 1
        return pendentes == 0


class RegistroHistorico(models.ModelPlus):
    historico = models.ForeignKeyPlus(Historico, verbose_name='Histórico', on_delete=models.CASCADE)
    componente = models.ForeignKeyPlus(Componente, verbose_name='Componente', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus(
        verbose_name='Tipo',
        default=ComponenteCurricular.FORMACAO_GERAL,
        choices=[
            (ComponenteCurricular.FORMACAO_GERAL, ComponenteCurricular.FORMACAO_GERAL),
            (ComponenteCurricular.FORMACAO_ESPECIFICA, ComponenteCurricular.FORMACAO_ESPECIFICA),
        ],
    )
    ano = models.CharFieldPlus(verbose_name='Ano', null=True)
    periodo = models.CharFieldPlus(verbose_name='Período', null=True, choices=[[str(x), str(x)] for x in range(1, 3)])
    turma = models.CharFieldPlus(verbose_name='Turma', null=True)
    nota = models.CharFieldPlus(verbose_name='Nota', null=True)
    qtd_faltas = models.CharFieldPlus(verbose_name='Faltas', null=True)
    carga_horaria = models.CharFieldPlus(verbose_name='C.H.', null=True)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=True, blank=True, choices=[[x, x] for x in ['', 'M', 'A', 'X']])
    periodo_matriz = models.IntegerField(verbose_name='Nível', null=True, choices=[[x, x] for x in range(1, 10)])
    opcional = models.BooleanField(verbose_name='Opcional', default=False, blank=True)

    class Meta:
        verbose_name = 'Registro de Histórico'
        verbose_name_plural = 'Registros de Histórico'

    def __str__(self):
        return f'{self.componente} - {self.periodo_matriz}º Período'

    def get_periodo_matriz(self):
        qs = self.historico.registrohistorico_set.filter(ano__isnull=False, periodo__isnull=False, componente=self.componente)
        i = (qs.filter(ano__lt=self.ano) | qs.filter(ano=self.ano, periodo__lte=self.periodo)).count()
        qs = self.historico.matriz.componentecurricular_set.filter(componente=self.componente).order_by('periodo')
        if i and qs.count() >= i:
            return qs[i - 1].periodo
        return None

    def get_situacao(self):
        if self.componente.nome == 'Educação Física' and self.nota == '999':
            return 'Dispensado'
        elif self.ano and self.periodo and self.situacao not in ['M', 'X']:
            return 'Aprovado'
        elif self.situacao == 'M':
            return 'Matriculado'
        elif self.situacao == 'X':
            return 'Cancelado'

    def get_frequencia(self):
        carga_horaria = self.get_carga_horaria()
        if carga_horaria is not None and carga_horaria.isdigit() and self.qtd_faltas is not None and self.qtd_faltas.isdigit():
            carga_horaria = int(carga_horaria)
            if carga_horaria:
                return int(100 - math.floor(int(self.qtd_faltas) * 100 / carga_horaria))
        return None

    def get_nota(self):
        if self.componente.nome in ('Programas de Saúde', 'Orientação Educacional'):
            return self.nota != '99' and self.nota or None
        elif self.componente.nome == 'Educação Física':
            return self.nota != '999' and self.nota or None
        else:
            return self.nota

    def get_carga_horaria(self):
        if self.historico.aluno.ano_letivo.ano < 1992:
            return self.carga_horaria
        else:
            qs = self.historico.matriz.componentecurricular_set.filter(componente=self.componente, periodo=self.periodo_matriz)
            return qs.exists() and str(qs.first().carga_horaria) or self.carga_horaria
