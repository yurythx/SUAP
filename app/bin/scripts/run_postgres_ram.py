#!/usr/bin/python

import os
import sys
from subprocess import PIPE, Popen, call

"""
   Usado para otimizar os testes, cria uma tablespace na memória RAM.
   Este monta o diretório /mnt apontando para a memória RAM
   e em seguida cria a tablespace ramfs no Postgres apontando para /mnt/pgdata.
"""


def main():
    thisfile = __file__

    if not os.access(thisfile, os.X_OK):
        sys.exit(
            f"""\nArquivo não executável, use o comando python antes.
Se desejar torná-lo executável, use:\nchmod +x {thisfile}\n"""
        )

    if os.geteuid() != 0:
        sys.exit("""\nVocê precisa ser root para rodar este comando.
Por favor use sudo antes de executar. Para não solicitar a senha,
edite o arquivo /etc/sudoers e dê permissão de sudo para este co-
mando ao seu usuário com a opção NOPASSWD, ex:
<username> ALL=NOPASSWD: /path/to/run_db_to_ramfs.py
\n""")
    if not os.path.exists('/mnt/pgdata'):
        print('Montando /mnt para a ramdisk (memória)')
        try:
            call(['mount', '-t', 'ramfs', 'none', '/mnt/'])
            call(['mkdir', '/mnt/pgdata'])
            call(['chown', '-R', 'postgres:postgres', '/mnt/pgdata'])
            call(['chmod', '-R', 'go-rwx', '/mnt/pgdata'])
        except Exception as e:
            print('CalledProcessError', str(e))
    else:
        print('Diretório /mnt/pgdata já existe.')

    try:
        scmd1 = 'sudo su -l postgres'
        scmd2 = b'psql -d postgres -c "CREATE TABLESPACE ramfs OWNER postgres LOCATION \'/mnt/pgdata\';"\n'
        scmd3 = b'psql -d postgres -c "GRANT CREATE ON TABLESPACE ramfs TO postgres;"\n'

        pid = Popen(scmd1, shell=True, stdout=PIPE, stdin=PIPE)
        pid.stdin.write(scmd2)
        pid.stdin.write(scmd3)

        pid.stdin.close()

        for line in pid.stdout.readlines():
            print(line)

        print(
            """Comando realizado com sucesso! Definir no aruivo settings o tablesapce padrão, use:
import sys
if 'test_suap' in sys.argv:
    DEFAULT_TABLESPACE = 'ramfs'
        """
        )
    except Exception as e:
        print('CalledProcessError', str(e))


if __name__ == '__main__':
    main()
