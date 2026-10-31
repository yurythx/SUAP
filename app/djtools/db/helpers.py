import psycopg
from django.db import transaction


def get_connection(conn):
    if not conn:
        from django.db import connection
    else:
        connection = psycopg.connect(**conn)
    return connection


@transaction.atomic
def get_dict(query_string, args=None, show_info=False, conn=None):
    connection = get_connection(conn)
    cursor = connection.cursor()
    try:
        cursor.execute(query_string, args or None)
    except Exception as e:
        connection.rollback()
        raise e
    col_names = [desc[0] for desc in cursor.description]
    result = []
    for row in cursor.fetchall():
        row_dict = dict(list(zip(col_names, row, strict=False)))
        result.append(row_dict)
    if not show_info:
        return result
    else:
        time = connection.queries and connection.queries[-1]['time'] or '?'
        return {'cols': col_names, 'time': time, 'result': result, 'total_rows': len(result)}


def get_dict_dict(query_string, key, conn=None):
    """Return a dict of dict.
    Ex:
    >>> sql = ''SELECT field1, field2 FROM table''
    >>> get_dict_dict(sql, field1)
    {'key1': {'field1': 'key1', 'field2': 'value'},
     'key2': {'field1': 'key2', 'field2': 'value'}}
    """
    dict = get_dict(query_string, conn)
    dict_dict = {}
    for d in dict:
        dict_dict[d[key]] = d

    return dict_dict


@transaction.atomic
def get_list(query_string, conn=None, args=None):
    connection = get_connection(conn)
    cursor = connection.cursor()
    try:
        cursor.execute(query_string, args or None)
    except Exception as e:
        connection._rollback()
        raise e
    result = []
    for row in cursor.fetchall():
        result.append(list(row))

    # If each row returns one value, let`s flat this
    # ((1,), (2,)) -> (1, 2)
    if result and len(result[0]) == 1:
        result = [row[0] for row in result]

    return result


@transaction.atomic
def get_list_extra(query_string, conn=None):
    connection = get_connection(conn)
    cursor = connection.cursor()
    try:
        cursor.execute(query_string)
    except Exception as e:
        connection.rollback()
        raise e
    colnames = [desc[0] for desc in cursor.description]
    result = list(cursor.fetchall())

    # If each row returns one value, let`s flat this
    # ((1,), (2,)) -> (1, 2)
    if result and len(result[0]) == 1:
        result = [row[0] for row in result]

    return {'rows': result, 'colnames': colnames}


# Util functions


def has_column(table_name, column_name, conn=None):
    try:
        sql = f"""select 1
                        from pg_catalog.pg_attribute a
                        where a.attrelid = (select oid
                                                    from pg_catalog.pg_class
                                                    where relname = '{table_name}')
                            and a.attname = '{column_name}';"""
        r = get_list(sql, conn=conn)[0]
        return bool(r)
    except Exception:
        return False


def has_columntype(table_name, column_name, column_type, conn=None):
    try:
        sql = f"""select 1
                        from pg_catalog.pg_attribute a
                        where a.attrelid = (select oid
                                                    from pg_catalog.pg_class
                                                    where relname = '{table_name}')
                            and a.attname = '{column_name}'
                            and pg_catalog.format_type(a.atttypid, a.atttypmod) = '{column_type}';"""
        r = get_list(sql, conn=conn)[0]
        return bool(r)
    except Exception:
        return False


def has_constraint(constraint_name, conn=None):
    try:
        sql = f"""SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}'"""
        r = get_list(sql, conn=conn)[0]
        return bool(r)
    except Exception:
        return False


def has_index(table_name, index_name, conn=None):
    try:
        sql = f"""SELECT 1 FROM pg_indexes WHERE tablename = '{table_name}' and indexname like '{index_name}%'"""
        r = get_list(sql, conn=conn)[0]
        return bool(r)
    except Exception:
        return False


def has_constrainttype(constraint_name, rel_table, conn=None):
    try:
        sql = f"""Select 1 FROM pg_constraint r
                    Inner Join pg_catalog.pg_class T on t.oid = r.conrelid
                    Inner Join pg_catalog.pg_class X on X.oid = r.confrelid
                    Where conname = '{constraint_name}' and X.relname = '{rel_table}';"""
        r = get_list(sql, conn=conn)[0]
        return bool(r)
    except Exception:
        return False


def get_table_columns(table_name, conn=None):
    connection = get_connection(conn)
    cursor = connection.cursor()
    cursor.execute(f'select * from {table_name} where 1 = 2')
    return [desc[0] for desc in cursor.description]


def get_table_column_size(table_name, column_name, conn=None):
    connection = get_connection(conn)
    cursor = connection.cursor()
    cursor.execute(f'select * from {table_name} where 1 = 2')
    for desc in cursor.description:
        if desc[0] == column_name:
            return str(desc[3])
    return ''


def is_null_column(table_name, column_name, conn=None):
    """Return True if table_name.column_name allows null values, False otherwise"""
    sql = f"""select attnotnull
                        from pg_catalog.pg_attribute a
                        where a.attrelid = (select oid
                                                    from pg_catalog.pg_class
                                                    where relname = '{table_name}')
                            and a.attname = '{column_name}';"""
    r = get_list(sql, conn=conn)[0]
    return not bool(r)


def table_exists(table_name, conn=None):
    r = get_list(f"select count(*) from information_schema.tables where table_name = '{table_name}'", conn=conn)
    return bool(r[0])


def drop_table(table_name, conn=None):
    if table_exists(table_name):
        connection = get_connection(conn)
        cursor = connection.cursor()
        cursor.execute(f'drop table {table_name}')
        connection._commit()


def sequence_is_owned_by(sequence, column, conn=None):
    """Return True if the sequence is owned by the column, False otherwise.
    The column param must be the table.colum format
    """
    tablename = column.split('.')[0]
    attname = column.split('.')[1]
    sql = f" SELECT pg_get_serial_sequence('{tablename}', '{attname}')"
    r = get_list(sql, conn=conn)
    s = None
    if r[0]:
        s = r[0]
        s = s.split('.')[1]
    return s == sequence
