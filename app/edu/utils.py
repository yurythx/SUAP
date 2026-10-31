from django.contrib.admin.filters import SimpleListFilter
from django.core.exceptions import ValidationError
from django.db.models import QuerySet

from comum.models import Ano
from djtools.crosstab.bidimensional import TabelaBidimensional
from djtools.utils import normalizar_nome_proprio
from edu.models import CursoCampus, Modalidade, Polo
from rh.models import UnidadeOrganizacional


def metadata(objeto):
    lista = []
    box = []
    methods_aux = []
    methods = []
    # Navega pelos atributos do objeto escolhido

    lista_fields_name = []
    for field in objeto._meta.fields:
        lista_fields_name.append(field.name)

    for field in objeto._meta.fields:
        field_name_aux = False
        box_name_aux = 'Dados gerais'
        if hasattr(objeto, 'fieldsets'):
            dict_fieldsets = dict(objeto.fieldsets)
            for t1, t2 in list(dict_fieldsets.items()):
                for t3 in list(t2.values()):
                    for t4 in t3:
                        if t4 == field.name:
                            field_name_aux = True
                            box_name_aux = t1
                        else:
                            if t4 not in lista_fields_name and t4 not in methods_aux:
                                methods_aux.append(t4)
                                methods.append({t1: t4})

        if not hasattr(objeto, 'fieldsets') or field_name_aux:
            url = ''

            # Recupera o valor do atributo
            if field.choices:
                valor = getattr(objeto, f'get_{field.name}_display')()
            elif field.__class__.__name__ == 'ImageWithThumbsField':
                imagem = objeto.__getattribute__(field.name)
                try:
                    valor = hasattr(imagem, 'url') and f'<img heigth="200" width="150" src="{imagem.url}" alt="Imagem de {objeto}"/>' or ''
                except Exception:
                    valor = ''
            else:
                valor = objeto.__getattribute__(field.name)

            # Verifica se o campo é estrangeiro
            if hasattr(field, 'related') and valor:
                url = ''
                # Verifica se o objeto possui o método get_absolute_url
                if hasattr(valor, 'get_absolute_url'):
                    url = str(valor.get_absolute_url())
                # O objeto estrangeiro precisa ser uma classe para gerar a url
                else:
                    app = valor._meta.app_label
                    modelo = valor.__class__.__name__
                    url = f'/edu/visualizar/{app}/{modelo}/{valor.pk}/'
            if box_name_aux not in box:
                box.append(box_name_aux)

            lista.append((normalizar_nome_proprio(field.verbose_name), valor, url, box_name_aux))

    for dict_methods in methods:
        for box_name, method_name in list(dict_methods.items()):
            if isinstance(method_name, str):
                method = getattr(objeto, method_name)
                lista.append((method_name.replace('get_', '').replace('_', ' ').capitalize(), method, '', box_name))
            elif isinstance(method_name, list | tuple):
                for m in method_name:
                    method = getattr(objeto, m)
                    lista.append((m.replace('get_', '').replace('_', ' ').capitalize(), method, '', box_name))

            if box_name not in box:
                box.append(box_name)

    lista.append(box)
    return lista


class TabelaResumoAluno(TabelaBidimensional):
    def __init__(self, qs_alunos):
        super().__init__(
            descricao='Total por Campus/Modalidade',
            qs=qs_alunos,
            vertical_key='curso_campus__diretoria__setor__uo__id',
            vertical_source=UnidadeOrganizacional,
            horizontal_key='curso_campus__modalidade__id',
            horizontal_source=Modalidade,
            vertical_header_name='Câmpus',
            vertical_include_null_value=True,  # manter, se desejado
        )


class TabelaResumoMatriculaPeriodo(TabelaBidimensional):
    def __init__(self, qs):
        super().__init__(
            descricao='Total por Câmpus/Modalidade',
            qs=qs,
            vertical_key='aluno__curso_campus__diretoria__setor__uo__id',
            vertical_source=UnidadeOrganizacional,
            horizontal_key='aluno__curso_campus__modalidade__id',
            horizontal_source=Modalidade,
            vertical_header_name='Câmpus',
            vertical_include_null_value=True,  # manter, se desejado
        )


class TabelaResumoMPCurso(TabelaBidimensional):
    def __init__(self, qs_alunos):
        super().__init__(
            descricao='Total por Curso',
            qs=qs_alunos,
            vertical_key='curso_campus__id',
            # select_related evita N+1: as uni_extra_columns abaixo acessam
            # diretoria.setor.uo e modalidade por linha de CursoCampus.
            vertical_source=CursoCampus.objects.select_related('diretoria__setor__uo', 'modalidade'),
            horizontal_key=None,
            horizontal_source=None,
            vertical_order_by='diretoria__setor__uo',  # equivalente ao comportamento anterior
            # Cabeçalho e colunas extras para o modo unidimensional (sem horizontal)
            uni_extra_columns=[
                ('Código', lambda o: o.codigo),
                ('Descrição', lambda o: o.descricao),
                ('Câmpus', lambda o: getattr(getattr(o.diretoria, 'setor', None), 'uo', '') or ''),
                ('Modalidade', lambda o: getattr(o.modalidade, 'descricao', '')),
            ],
        )


class TabelaPoloAnoNivelEnsino(TabelaBidimensional):
    def __init__(self, qs_alunos):
        super().__init__(
            descricao='Total de Alunos no Polo por Ano de Ingresso',
            qs=qs_alunos,
            vertical_key='ano_letivo',
            vertical_source=Ano,
            horizontal_key='curso_campus__modalidade__id',
            horizontal_source=Modalidade,
            vertical_header_name='Ano de Ingresso',
        )


class TabelaAlunoPoloNivelEnsino(TabelaBidimensional):
    def __init__(self, qs_alunos):
        super().__init__(
            descricao='Total de Alunos por Polo e Nível de Ensino',
            qs=qs_alunos,
            vertical_key='polo',
            vertical_source=Polo,
            horizontal_key='curso_campus__modalidade__id',
            horizontal_source=Modalidade,
            vertical_header_name='Polo',
            vertical_include_null_value=True,  # se houver registros sem polo
        )


class TabelaAlunoCursoCampusPolo(TabelaBidimensional):
    def __init__(self, qs_alunos):
        super().__init__(
            descricao='Total de Alunos por Curso e Polo',
            qs=qs_alunos,
            vertical_key='curso_campus__id',
            vertical_source=CursoCampus,
            horizontal_key='polo',
            horizontal_source=Polo,
            vertical_header_name='Curso',
            vertical_order_by='diretoria__setor__uo',
            # Em bidimensional, rotulagem padrão (str) costuma bastar; ajustar se necessário:
            # vertical_label=lambda cc: cc.descricao,
            # horizontal_label=lambda p: p.descricao,
        )


class TabelaMPPoloNivelEnsino(TabelaBidimensional):
    def __init__(self, qs):
        super().__init__(
            'Total de Alunos por Polo e Nível de Ensino',
            qs=qs,
            vertical_source=Polo,
            vertical_key='polo',
            horizontal_source=Modalidade,
            horizontal_key='curso_campus__modalidade__id',
        )


class TabelaCampusPorModalidade(TabelaBidimensional):
    """
    Tabela usada na view 'detalhar_variavel' para exibir dados de alunos
    por Câmpus (UO) e Modalidade, somando duas fontes (matrículas e alunos).

    Observações:
    - Quando 'uo' é informado, mantém-se o comportamento legado: a tabela
      renderiza apenas a linha de 'TOTAL' (somatório geral).

    """

    def __init__(
        self, qs_matriculas1: QuerySet | None = None, qs_alunos: QuerySet | None = None, uo: UnidadeOrganizacional | int | None = None
    ) -> None:
        from edu.models import Diretoria, Modalidade

        # Domínio vertical (UOs de campus) e horizontal (modalidades)
        uos_campus_ids = Diretoria.objects.values('setor__uo').distinct()
        uos_qs = UnidadeOrganizacional.objects.suap().filter(pk__in=uos_campus_ids)

        if uo:
            vertical_ids = [getattr(uo, 'pk', uo)]
        else:
            vertical_ids = list(uos_qs.values_list('id', flat=True))

        horizontal_ids = list(Modalidade.objects.values_list('id', flat=True))

        super().__init__(
            descricao='CAMPUS x Modalidade',
            # qs “base” pode ser qualquer QS (não será usado para .values_list quando IDs são informados)
            qs=qs_alunos or qs_matriculas1 or UnidadeOrganizacional.objects.none(),
            vertical_key='curso_campus__diretoria__setor__uo__id',
            vertical_source=UnidadeOrganizacional,
            horizontal_key='curso_campus__modalidade__id',
            horizontal_source=Modalidade,
            vertical_header_name='CAMPUS',
            vertical_ids=vertical_ids,
            horizontal_ids=horizontal_ids,
            count_func=self._count_alunos_matr_periodo_factory(qs_matriculas1, qs_alunos),
            # manter totais/linha "não identificado" conforme necessidade:
            vertical_include_null_value=False,
        )
        if uo:
            # com um único campus a linha do campus já é o somatório geral: expõe só ela, rotulada como TOTAL
            self.registros = [{**linha, 0: 'TOTAL'} for linha in self.registros]

    def _count_alunos_matr_periodo_factory(self, qs_matriculas1, qs_alunos):
        """
        Retorna uma função count_func(qs, lookup) que soma:
          - Matriculas: aluno__curso_campus__... (uo/modalidade)
          - Alunos:     curso_campus__...        (uo/modalidade)
        """

        def _count_func(_qs, lookup: dict) -> int:
            uo_id = lookup.get('curso_campus__diretoria__setor__uo__id')
            modalidade_id = lookup.get('curso_campus__modalidade__id')
            total = 0
            if qs_matriculas1 is not None:
                total += qs_matriculas1.filter(
                    aluno__curso_campus__diretoria__setor__uo__id=uo_id,
                    aluno__curso_campus__modalidade__id=modalidade_id,
                ).count()
            if qs_alunos is not None:
                total += qs_alunos.filter(
                    curso_campus__diretoria__setor__uo__id=uo_id,
                    curso_campus__modalidade__id=modalidade_id,
                ).count()
            return total

        return _count_func


class SolicitacaoFilter(SimpleListFilter):
    title = 'tipo'
    parameter_name = 'tipo'

    def lookups(self, request, model_admin):
        return (('relancamento_etapa', 'Solicitações de Relançamento de Etapa'), ('prorrogacao_etapa', 'Solicitações de Prorrogação de Etapa'))

    def queryset(self, request, queryset):
        if self.value() == 'relancamento_etapa':
            return queryset.filter(solicitacaorelancamentoetapa__isnull=False)
        if self.value() == 'prorrogacao_etapa':
            return queryset.filter(solicitacaoprorrogacaoetapa__isnull=False)


def validar_matricula_de_aluno_em_diario(aluno, diario, ignorar_quebra_requisito=False):
    """
    Valida se um aluno pode ser matriculado em um determinado diário, levando em consideração
    restrições específicas e possíveis conflitos de horário.

    :raises: ValidationError - Se o aluno ou diário não for informado ou se houver algum impedimento para matrícula.
    """
    from edu.models import Diario, MatriculaDiario

    if aluno is None:
        raise ValidationError('O aluno não foi informado.')
    if diario is None:
        raise ValidationError('O diário não foi informado.')

    pode_ser_matriculado, msg_validacao = aluno.pode_ser_matriculado_no_diario(diario, ignorar_quebra_requisito=ignorar_quebra_requisito)
    if not pode_ser_matriculado:
        raise ValidationError(msg_validacao)

    matricula_periodo = aluno.matriculaperiodo_set.get(ano_letivo=diario.ano_letivo, periodo_letivo=diario.periodo_letivo)
    ids_diarios = list(
        matricula_periodo.matriculadiario_set.exclude(situacao=MatriculaDiario.SITUACAO_CANCELADO).values_list('diario__pk', flat=True)
    )
    diarios_com_choque_horario = Diario.get_diarios_choque_horario(ids_diarios, diario_pivot=diario)
    if diarios_com_choque_horario:
        raise ValidationError(
            f'Esta matrícula causa choque de horário com os seguintes diários em que o aluno '
            f'está matriculado: {", ".join([str(diario) for diario in diarios_com_choque_horario])}'
        )
