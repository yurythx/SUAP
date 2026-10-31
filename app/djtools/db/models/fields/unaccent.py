import hashlib

from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models.lookups import Contains, EndsWith, Exact, IContains, IEndsWith, IExact, In, IStartsWith, StartsWith

from .string import CharFieldPlus

UNACCENT_FUNCTION = 'f_unaccent'  # Nome da função SQL que criamos para remover acentos
MAX_LENGTH = 63


class PostgresBTreeIndex(models.Index):
    max_name_length = MAX_LENGTH


class PostgresGinIndex(GinIndex):
    max_name_length = MAX_LENGTH


class UnaccentedLookupMixin:
    def process_lhs(self, compiler, connection, lhs=None):
        lhs, lhs_params = super().process_lhs(compiler, connection)
        # lhs = UPPER("pessoa"."nome"::text)
        if 'UPPER' in lhs:
            lhs = lhs[6:-1]
        return lhs, lhs_params

    def as_sql(self, compiler, connection):
        lhs, params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params.extend(rhs_params)
        return f'{UNACCENT_FUNCTION}({lhs}) {self.operator} {UNACCENT_FUNCTION}({rhs})', params


class FUnaccent(models.Func):
    function = UNACCENT_FUNCTION


def generate_index_name(table_name, column_name, suffix='unac_btree'):
    # Gera o hash para garantir unicidade
    hash_str = hashlib.md5(f'{table_name}_{column_name}'.encode()).hexdigest()[:6]

    # O tamanho fixo será: hash (6) + tamanho do sufixo + 3 underscores
    fixed_length = len(hash_str) + len(suffix) + 3

    # O espaço que sobra distribuímos entre o nome da tabela e da coluna
    remaining_size = MAX_LENGTH - fixed_length
    half = remaining_size // 2

    # Corta as strings. Se sobrar 1 caractere ímpar, jogamos para a coluna.
    t_name = table_name[:half]
    c_name = column_name[: remaining_size - half]

    return f'{t_name}_{c_name}_{hash_str}_{suffix}'


class UnaccentField(CharFieldPlus):
    """
    Campo que utiliza Collation do Postgres para ignorar acentos e case
    de forma nativa no banco de dados.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 255)
        kwargs.setdefault('db_index', True)

        # Mantendo sua lógica de widget_attrs do seu código original
        self.widget_attrs = kwargs.pop('widget_attrs', {})
        if 'width' in kwargs:
            self.widget_attrs['style'] = f'width: {kwargs.pop("width")}px;'

        super().__init__(*args, **kwargs)

    def contribute_to_class(self, cls, name, private_only=False):
        super().contribute_to_class(cls, name, private_only)

        # Adiciona um índice funcional automaticamente ao Model
        if self.db_index and not cls._meta.abstract:
            index_name = generate_index_name(cls._meta.db_table, name, 'unac_btree')
            gin_index_name = generate_index_name(cls._meta.db_table, name, 'unac_gin')

            # Criamos um índice que casa exatamente com a query: f_unaccent(UPPER(campo))
            # Usamos o Gin ou B-Tree dependendo da sua necessidade, aqui B-Tree resolve
            index = PostgresBTreeIndex(
                FUnaccent(models.F(name)),
                name=index_name,  # Limite de caracteres do Postgres
            )

            index_gin = PostgresGinIndex(
                OpClass(FUnaccent(models.F(name)), name='gin_trgm_ops'),
                name=gin_index_name,
            )
            # 1. Adicionamos em _meta.indexes para o ORM usar em tempo de execução
            if cls._meta.indexes is None:
                cls._meta.indexes = []

            if not any(idx.name == index_name for idx in cls._meta.indexes):
                cls._meta.indexes.append(index)
            if not any(idx.name == gin_index_name for idx in cls._meta.indexes):
                cls._meta.indexes.append(index_gin)

            # 2. Adicionamos em _meta.original_attrs para o makemigrations detectar
            if 'indexes' not in cls._meta.original_attrs:
                cls._meta.original_attrs['indexes'] = []
            else:
                # O usuário pode ter definido 'indexes' como uma tupla na class Meta
                cls._meta.original_attrs['indexes'] = list(cls._meta.original_attrs['indexes'])

            original_indexes = cls._meta.original_attrs['indexes']

            if not any(idx.name == index_name for idx in original_indexes):
                original_indexes.append(index)
            if not any(idx.name == gin_index_name for idx in original_indexes):
                original_indexes.append(index_gin)


class UnaccentExact(UnaccentedLookupMixin, Exact):
    operator = '='


class UnaccentIExact(UnaccentedLookupMixin, IExact):
    operator = 'LIKE'


class UnaccentContains(UnaccentedLookupMixin, Contains):
    operator = 'LIKE'


class UnaccentIContains(UnaccentedLookupMixin, IContains):
    operator = 'LIKE'


class UnaccentIStartsWith(UnaccentedLookupMixin, IStartsWith):
    operator = 'LIKE'


class UnaccentStartsWith(UnaccentedLookupMixin, StartsWith):
    operator = 'LIKE'


class UnaccentEndsWith(UnaccentedLookupMixin, EndsWith):
    operator = 'LIKE'


class UnaccentIEndsWith(UnaccentedLookupMixin, IEndsWith):
    operator = 'LIKE'


class UnaccentIn(UnaccentedLookupMixin, In):
    operator = 'IN'

    def as_sql(self, compiler, connection):
        lhs, params = self.process_lhs(compiler, connection)
        _, rhs_params = self.process_rhs(compiler, connection)
        placeholder = '(' + ', '.join(f'{UNACCENT_FUNCTION}(%s)' for expr in rhs_params) + ')'
        params.extend(rhs_params)
        # Aplicamos F_UNACCENT em ambos os lados para garantir a correspondência
        return f'{UNACCENT_FUNCTION}({lhs}) IN {placeholder}', params


lookups = [
    UnaccentExact,
    UnaccentIExact,
    UnaccentContains,
    UnaccentIContains,
    UnaccentStartsWith,
    UnaccentIStartsWith,
    UnaccentEndsWith,
    UnaccentIEndsWith,
    UnaccentIn,
]
for lookup in lookups:
    UnaccentField.register_lookup(lookup)
