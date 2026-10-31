from typing import Any

from django.conf import settings
from django.db.models.query import QuerySet
from ninja import Schema
from ninja.pagination import PaginationBase
from pydantic import Field


class Pagination(PaginationBase):
    """
    Classe de paginação personalizada.

    Attributes:
        items_attribute (str): Nome do atributo que contém os itens paginados.
        page_size (int): Número de itens por página.
    """

    items_attribute: str = 'results'

    def __init__(self, page_size: int = 100, **kwargs: Any) -> None:
        """
        Inicializa a classe de paginação com o tamanho da página.

        Args:
            page_size (int): Número de itens por página.
            **kwargs: Argumentos adicionais.
        """
        self.page_size = page_size
        super().__init__(**kwargs)

    # only `skip` param, defaults to 5 per page
    class Input(Schema):
        """
        Esquema de entrada para paginação.

        Attributes:
            page (int): Número da página, começando de 1.
        """

        page: int = Field(1, ge=1)

    class Output(Schema):
        """
        Esquema de saída para paginação.

        Attributes:
            results (List[Any]): Lista de itens paginados.
            count (int): Contagem total de itens.
            next (str | None): URL para a próxima página, se houver.
            previous (str | None): URL para a página anterior, se houver.
        """

        results: list[Any]  # `items` is a default attribute
        count: int
        next: str | None
        previous: str | None

    def paginate_queryset(self, queryset_or_list, pagination: Input, **params):
        """
        Pagina um queryset com base nos parâmetros de entrada.

        Args:
            queryset_or_list: Queryset ou lista a ser paginado.
            pagination (Input): Parâmetros de entrada para paginação.
            **params: Parâmetros adicionais.

        Returns:
            dict: Dicionário contendo os itens paginados, contagem total, e URLs para próxima e anterior páginas.
        """
        if not isinstance(queryset_or_list, QuerySet):
            return {
                'results': queryset_or_list,
                'count': len(queryset_or_list),
                'next': None,
                'previous': None,
            }
        queryset = queryset_or_list
        page = pagination.page
        offset = (page - 1) * self.page_size
        request = params['request']
        get = request.GET.copy()
        params_previous = get.copy()
        params_next = get.copy()
        params_previous['page'] = page - 1
        params_next['page'] = page + 1
        has_previous = page > 1
        has_next = page * self.page_size < queryset.count()
        base_url = f'{settings.SITE_URL}{request.path}?'
        return {
            'results': queryset[offset : offset + self.page_size],
            'count': queryset.count(),
            'next': has_next and f'{base_url}{params_next.urlencode()}' or None,
            'previous': has_previous and f'{base_url}{params_previous.urlencode()}' or None,
        }
