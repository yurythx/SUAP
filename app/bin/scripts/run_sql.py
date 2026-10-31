import argparse

import psycopg

connection = None
cursor = None
parser = argparse.ArgumentParser()
parser.add_argument('-d', '--database', help='database', default='')
parser.add_argument('-u', '--user', help='User', default='postgres')
parser.add_argument('-W', '--password', help='Password', default='')
parser.add_argument('-t', '--host', help='Host', default='localhost')
parser.add_argument('-p', '--port', help='Port', default='5432')
parser.add_argument('-l', '--limit', help='Limit', default=100, type=int)
parser.add_argument('-c', '--command', help='Command', required=True)
args = parser.parse_args()


def show_query(cursor, qry):
    cursor.execute(qry)
    print('Comando executado com sucesso.')
    try:
        rows = cursor.fetchmany(args.limit)
    except Exception:
        rows = None
    if rows:
        for row in rows:
            print(row)
        print('Fim dos resultados.')
    else:
        print('Esta consulta não produziu nenhum resultado.')


try:
    connection = psycopg.connect(user=args.user, password=args.password, host=args.host, port=args.port, dbname=args.database, autocommit=True)

    cursor = connection.cursor()
    print('Informações do servidor:')
    print(connection.info.dsn, '\n')
    show_query(cursor, args.command)
except Exception as error:
    print('Erro de execução com o PostgreSQL')
    raise error
finally:
    if connection:
        if cursor:
            cursor.close()
        connection.close()
        print('Conexão finalizada.')
