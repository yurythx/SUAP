# tools/crosstab/bidimensional.py

from collections.abc import Callable, Iterable, Sequence
from django.db.models import Count, QuerySet, Model, Manager
from django.template.loader import render_to_string


def _as_queryset(source):
    """
    Aceita Model, Manager ou QuerySet e retorna algo com .filter(...)
    sem impor import de modelos dentro de djtools.
    """
    if source is None:
        return None
    # QuerySet e Manager expõem .filter; Model expõe .objects
    if hasattr(source, 'filter'):
        return source  # QuerySet ou Manager
    if hasattr(source, 'objects'):
        return source.objects  # Model -> Manager
    raise TypeError('Fonte inválida: informe um Model/Manager/QuerySet.')


class TabelaBidimensional:
    """
    Tabela de resumo (crosstab) genérica, desacoplada de modelos de domínio.

    Parâmetros essenciais
    ---------------------
    descricao: título/descrição da tabela.
    qs: QuerySet de fatos sobre o qual serão feitos os .filter(**lookup).count().
    vertical_key: string do lookup para a dimensão vertical (ex.: 'uo', 'curso_campus__id', etc.).
    vertical_source: Model/Manager/QuerySet da dimensão vertical (filtrável por id__in).
    horizontal_key: (opcional) string do lookup para a dimensão horizontal.
    horizontal_source: (opcional) Model/Manager/QuerySet da dimensão horizontal.

    Parametrizações úteis
    ---------------------
    vertical_order_by: string para ordenar vertical (ex.: 'nome', 'diretoria__setor__uo').
    vertical_label/horizontal_label: Callable(obj) -> str para rótulos.
    vertical_header_name: cabeçalho da 1ª coluna (default 'Categoria').
    total_label: rótulo da coluna/linha de total (default 'TOTAL').
    not_identified_label: rótulo para linha "não identificado" (default).
    vertical_include_null_value: se True, inclui linha para vertical_key IS NULL.
    template_name: template a renderizar em __str__.
    uni_extra_columns: lista de (nome_coluna, func(obj)->str) para tabela unidimensional,
        adicionando colunas antes da contagem (resolve o antigo caso CursoCampus).
    """

    def __init__(
        self,
        descricao: str,
        qs,
        *,
        vertical_key: str,
        vertical_source: Model | Manager | QuerySet,
        horizontal_key: str | None = None,
        horizontal_source: Model | Manager | QuerySet = None,
        vertical_order_by: str | None = None,
        vertical_label: Callable = str,
        horizontal_label: Callable = str,
        vertical_header_name: str = 'Categoria',
        total_label: str = 'TOTAL',
        not_identified_label: str = 'Não identificado',
        vertical_include_null_value: bool = False,
        template_name: str = 'djtools/templates/crosstab/bidimensional.html',
        uni_extra_columns: Sequence[tuple[str, Callable]] | None = None,
        count_func: Callable | None = None,
        vertical_ids: Iterable[int] | None = None,
        horizontal_ids: Iterable[int] | None = None,
    ):
        self.descricao = descricao
        self.template_name = template_name
        self.align_column = 1  # índice (base 1) da primeira coluna numérica

        horizontal_objects = self._resolve_horizontal(qs, horizontal_key, horizontal_source, horizontal_ids)
        vertical_objects = self._resolve_vertical(qs, vertical_key, vertical_source, vertical_ids, vertical_order_by)
        agg = self._build_agg(qs, count_func, horizontal_objects, vertical_key, horizontal_key)

        self.colunas, self.align_column = self._build_columns(
            horizontal_objects, horizontal_label, vertical_header_name, total_label, uni_extra_columns
        )

        ctx = {
            'qs': qs,
            'agg': agg,
            'count_func': count_func,
            'vertical_key': vertical_key,
            'horizontal_key': horizontal_key,
            'vertical_label': vertical_label,
            'horizontal_objects': horizontal_objects,
            'uni_extra_columns': uni_extra_columns,
            'total_label': total_label,
            'not_identified_label': not_identified_label,
            'vertical_include_null_value': vertical_include_null_value,
        }
        self.registros = self._build_rows(vertical_objects, ctx)

    @staticmethod
    def _resolve_horizontal(qs, horizontal_key, horizontal_source, horizontal_ids):
        """Resolve os objetos da dimensão horizontal (vazio no modo unidimensional)."""
        if horizontal_key and horizontal_source:
            hsrc = _as_queryset(horizontal_source)
            if horizontal_ids is not None:
                h_ids = horizontal_ids
            elif qs is None:
                raise ValueError(
                    "Para inferir horizontal_ids automaticamente é necessário fornecer 'qs'. "
                    "Alternativamente, informe 'horizontal_ids' explicitamente."
                )
            else:
                h_ids = qs.values_list(horizontal_key, flat=True).distinct()
            return list(hsrc.filter(id__in=h_ids))

        if horizontal_key or horizontal_source:
            # Estado híbrido: um parâmetro fornecido sem o outro
            raise ValueError(
                "Parâmetros horizontais incoerentes: informe 'horizontal_key' E 'horizontal_source' "
                'para usar o modo bidimensional, ou deixe ambos como None para o modo unidimensional.'
            )

        # Modo unidimensional (sem eixo horizontal)
        return []

    @staticmethod
    def _resolve_vertical(qs, vertical_key, vertical_source, vertical_ids, vertical_order_by):
        """Resolve os objetos da dimensão vertical (sempre obrigatória)."""
        if not vertical_key or not vertical_source:
            raise ValueError("Parâmetros verticais incoerentes: é obrigatório informar 'vertical_key' e 'vertical_source' para montar a tabela.")

        vsrc = _as_queryset(vertical_source)
        if vertical_ids is not None:
            v_ids = vertical_ids
        elif qs is None:
            raise ValueError(
                "Para inferir vertical_ids automaticamente é necessário fornecer 'qs'. Alternativamente, informe 'vertical_ids' explicitamente."
            )
        else:
            v_ids = qs.values_list(vertical_key, flat=True).distinct()

        vertical_qs = vsrc.filter(id__in=v_ids)
        if vertical_order_by:
            vertical_qs = vertical_qs.order_by(vertical_order_by)
        return list(vertical_qs)

    @staticmethod
    def _build_agg(qs, count_func, horizontal_objects, vertical_key, horizontal_key):
        """
        Pré-agrega as contagens em UMA query (GROUP BY), evitando o N+1 de
        qs.filter(**lookup).count() por célula. Aplicado apenas no caminho
        padrão; quando count_func é fornecida (somatório de múltiplas fontes),
        mantém-se o comportamento original (dict vazio + fallback no count_func).
        """
        agg: dict = {}
        if count_func is not None or qs is None:
            return agg
        # order_by() limpa qualquer ordenação herdada do qs, que o Django
        # dobraria no GROUP BY e fragmentaria as contagens.
        base = qs.order_by()
        if horizontal_objects:
            for row in base.values(vertical_key, horizontal_key).annotate(qtd=Count('id')):
                agg[(row[vertical_key], row[horizontal_key])] = row['qtd']
        else:
            for row in base.values(vertical_key).annotate(qtd=Count('id')):
                agg[row[vertical_key]] = row['qtd']
        return agg

    @staticmethod
    def _build_columns(horizontal_objects, horizontal_label, vertical_header_name, total_label, uni_extra_columns):
        """Monta o cabeçalho e devolve (colunas, align_column)."""
        colunas: list[str] = []
        if horizontal_objects:
            colunas.append(vertical_header_name)
            for ho in horizontal_objects:
                colunas.append(horizontal_label(ho))
            colunas.append(total_label)
            return colunas, 2  # a partir da 2ª coluna começam os numéricos
        if uni_extra_columns:
            colunas.extend([name for name, _ in uni_extra_columns])
            colunas.append('QTD')
            return colunas, len(uni_extra_columns) + 1
        colunas.extend([vertical_header_name, 'Quantidade'])
        return colunas, 2

    def _subtotal(self, ctx, lookup, v_val, h_val=None):
        """Contagem de uma célula: via count_func (legado) ou via dict pré-agregado."""
        if ctx['count_func'] is not None:
            return ctx['count_func'](ctx['qs'], lookup)
        if ctx['horizontal_objects']:
            return ctx['agg'].get((v_val, h_val), 0)
        return ctx['agg'].get(v_val, 0)

    def _bi_row(self, vobj, registro_final, ctx):
        """Linha do modo bidimensional (uma célula por objeto horizontal + total)."""
        registro = {0: ctx['vertical_label'](vobj)}
        linha_total = 0
        i = 1
        for hobj in ctx['horizontal_objects']:
            lookup = {ctx['vertical_key']: getattr(vobj, 'id', None), ctx['horizontal_key']: getattr(hobj, 'id', None)}
            subtotal = self._subtotal(ctx, lookup, getattr(vobj, 'id', None), getattr(hobj, 'id', None))
            registro[i] = subtotal
            registro_final[i] += subtotal
            linha_total += subtotal
            i += 1
        registro[i] = linha_total  # total da linha
        return registro, linha_total

    def _uni_row(self, vobj, ctx):
        """Linha do modo unidimensional (colunas textuais extras + contagem)."""
        registro = {}
        i = 0
        if ctx['uni_extra_columns']:
            for _, fn in ctx['uni_extra_columns']:
                registro[i] = fn(vobj)
                i += 1
        else:
            registro[i] = ctx['vertical_label'](vobj)
            i += 1
        lookup = {ctx['vertical_key']: getattr(vobj, 'id', None)}
        linha_total = self._subtotal(ctx, lookup, getattr(vobj, 'id', None))
        registro[i] = linha_total
        return registro, linha_total

    def _append_null_row(self, registros, registro_final, ctx):
        """Linha “Não identificado” (vertical_key IS NULL). Devolve o total da linha."""
        vertical_key = ctx['vertical_key']
        registro = {0: ctx['not_identified_label']}
        linha_total = 0
        if ctx['horizontal_objects']:
            i = 1
            for hobj in ctx['horizontal_objects']:
                lookup = {f'{vertical_key}__isnull': True, ctx['horizontal_key']: getattr(hobj, 'id', None)}
                subtotal = self._subtotal(ctx, lookup, None, getattr(hobj, 'id', None))
                registro[i] = subtotal
                registro_final[i] += subtotal
                linha_total += subtotal
                i += 1
            registro[i] = linha_total
        else:
            lookup = {f'{vertical_key}__isnull': True}
            linha_total = self._subtotal(ctx, lookup, None)
            # posição da coluna numérica depende do cabeçalho montado
            registro[self.align_column - 1] = linha_total
        registros.append(registro)
        return linha_total

    def _build_rows(self, vertical_objects, ctx):
        """Monta todas as linhas (dados + “não identificado” + rodapé de totais)."""
        horizontal_objects = ctx['horizontal_objects']
        registros: list[dict] = []
        registro_final = {0: ctx['total_label']}
        for i in range(1, len(horizontal_objects) + 1):
            registro_final[i] = 0

        total_final = 0
        for vobj in vertical_objects:
            if horizontal_objects:
                registro, linha_total = self._bi_row(vobj, registro_final, ctx)
            else:
                registro, linha_total = self._uni_row(vobj, ctx)
            total_final += linha_total
            registros.append(registro)

        if ctx['vertical_include_null_value']:
            total_final += self._append_null_row(registros, registro_final, ctx)

        n_linhas = len(vertical_objects) + (1 if ctx['vertical_include_null_value'] else 0)
        if horizontal_objects and n_linhas > 1:
            registro_final[len(horizontal_objects) + 1] = total_final
            registros.append(registro_final)
        return registros

    def __str__(self):
        return render_to_string(self.template_name, {'tabela': self, 'descricao': self.descricao})
