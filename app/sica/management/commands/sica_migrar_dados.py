from dbfread import DBF

from djtools.management.commands import BaseCommandPlus
from djtools.utils import normalizar_nome_proprio
from edu.models import ConfiguracaoLivro
from edu.models.alunos import Aluno
from sica.models import Componente, ComponenteCurricular, Historico, Matriz, RegistroHistorico


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        RegistroHistorico.objects.all().delete()
        Historico.objects.all().delete()
        ComponenteCurricular.objects.all().delete()
        Matriz.objects.all().delete()
        Componente.objects.all().delete()

        matrizes = {}
        disciplinas = {}

        for matriz in [
            {'id': 11, 'nome': 'Técnico em Estradas', 'codigo': '11'},
            {'id': 12, 'nome': 'Técnico em Edificações', 'codigo': '12'},
            {'id': 13, 'nome': 'Técnico em Saneamento', 'codigo': '13'},
            {'id': 21, 'nome': 'Técnico em Mecânica', 'codigo': '21'},
            {'id': 22, 'nome': 'Técnico em Eletrônica', 'codigo': '22'},
            {'id': 31, 'nome': 'Técnico em Mineração', 'codigo': '31'},
            {'id': 32, 'nome': 'Técnico em Geologia', 'codigo': '32'},
        ]:
            matrizes[int(matriz['id'])] = matriz

        for matriz_data in matrizes.values():
            Matriz.objects.get_or_create(**matriz_data)

        for record in DBF('/tmp/SICANE00.DBF', raw=True):
            codigo = record['EN_CDDI'].strip()[-3:].rjust(3, '0')
            nome = record['EC_NMDI'].strip()
            sigla = record['EC_SGDI'].strip()
            disciplinas[codigo] = {'nome': normalizar_nome_proprio(nome), 'sigla': sigla, 'codigo': codigo}

        for disciplina_data in disciplinas.values():
            Componente.objects.get_or_create(**disciplina_data)

        for periodo, matriz_id, s in [
            (1, 11, '001005007011012013014015017018'),
            (2, 11, '001003004005006011012013018'),
            (3, 11, '001003005011012019020021022126'),
            (4, 11, '001003005129011020023024'),
            (5, 11, '001003005129011020023025026'),
            (6, 11, '001005011025027028029'),
            (7, 11, '002005010028029030031032'),
            (1, 12, '001005007011012013014015017018'),
            (2, 12, '001003004005006011012013018'),
            (3, 12, '001003005011012034021037126'),
            (4, 12, '001003005129011035024036'),
            (5, 12, '001003005129011033035036038'),
            (6, 12, '001005011033038039040041'),
            (7, 12, '002005010038041042032'),
            (1, 13, '001005007011012013014015017018'),
            (2, 13, '001003004005006011012013018'),
            (3, 13, '001003005011012044045021126'),
            (4, 13, '001003005129011053054024048'),
            (5, 13, '001003005129011043046049051'),
            (6, 13, '001005011047049051052'),
            (7, 13, '002005010050052032042'),
            (1, 21, '001005007011012013014015017018'),
            (2, 21, '001003004005006011012013018'),
            (3, 21, '001003005011012056021060061062126'),
            (4, 21, '001003005129011055057062074'),
            (5, 21, '001003005129011062063064074'),
            (6, 21, '001005011065066067072074'),
            (7, 21, '002005010127068070071077'),
            (1, 22, '001005007011012013014015017018'),
            (2, 22, '001003004005006011012013018'),
            (3, 22, '001003005011012078080021126'),
            (4, 22, '001003005129011078079083'),
            (5, 22, '001003005129011084086087'),
            (6, 22, '001005011081128086088093'),
            (7, 22, '002005010085089090091092'),
            (1, 31, '001005007011012013014015017018'),
            (2, 31, '001003004005006011012013018'),
            (3, 31, '001003005011012095021097098126'),
            (4, 31, '001003005129011098099105'),
            (5, 31, '001003005129011096100101105'),
            (6, 31, '001005011094128103107108109'),
            (7, 31, '002005010102103104106107108'),
            (1, 32, '001005007011012013014015017018'),
            (2, 32, '001003004005006011012013018'),
            (3, 32, '001003005011012111097098021126'),
            (4, 32, '001003005129011098117105'),
            (5, 32, '001003005129011112113114096105'),
            (6, 32, '001005011094115116118119128'),
            (7, 32, '002005010102118120121122123125'),
        ]:
            for i, j in [(0, 3), (3, 6), (6, 9), (9, 12), (12, 15), (15, 18), (18, 21), (21, 24), (24, 27), (27, 30), (30, 33), (33, 36), (36, 39)]:
                codigo = s[i:j]
                if codigo:
                    componente = Componente.objects.get(codigo=codigo.strip())
                    qs = ComponenteCurricular.objects.filter(matriz_id=matriz_id, periodo=periodo, componente=componente)
                    if not qs.exists():
                        ComponenteCurricular.objects.create(matriz_id=matriz_id, periodo=periodo, componente=componente)

        for record in DBF('/tmp/SICANB00.DBF', raw=True):
            matricula = record['AN_MATR'].strip()
            aluno = Aluno.objects.filter(matricula=matricula).first()
            if aluno:
                ano = record['BN_PELE'].strip()[0:-1]
                periodo = record['BN_PELE'][-1]
                turma = record['BN_TURM'].strip()
                situacao = record['BC_SITF'].strip()
                if not periodo.isdigit():
                    periodo = None
                if not ano.isdigit():
                    ano = None
                historico = Historico.objects.filter(aluno=aluno).first()
                if not historico:
                    historico = Historico.objects.create(aluno=aluno)
                for key in list(record.keys()):
                    if key not in ('AN_MATR', 'BN_PELE', 'BN_TURM', 'BC_SITF'):
                        value = record[key].strip()
                        if value and value != '0':
                            if value[0:3]:
                                codigo_disciplina = value[0:3].strip().rjust(3, '0')
                                nota_disciplina = value[3:6].strip() or None
                                faltas_disciplina = value[6:8].strip() or None
                                ch_disciplina = value[8:11].strip() or None
                                ano = value[11:15]
                                if not ano.isdigit():
                                    ano = None
                                else:
                                    ano = int(ano)
                                periodo = value[15:16]
                                if not periodo.isdigit():
                                    periodo = None
                                else:
                                    periodo = int(periodo)
                                componente = Componente.objects.filter(codigo=codigo_disciplina).first()
                                if not componente:
                                    componente = Componente.objects.create(codigo=codigo_disciplina)
                                RegistroHistorico.objects.create(
                                    historico=historico,
                                    componente=componente,
                                    nota=nota_disciplina,
                                    qtd_faltas=faltas_disciplina,
                                    ano=ano,
                                    periodo=periodo,
                                    turma=turma,
                                    situacao=situacao,
                                    carga_horaria=ch_disciplina,
                                )

        if not ConfiguracaoLivro.objects.filter(descricao='SICA').exists():
            configuracao = ConfiguracaoLivro.objects.create(
                descricao='SICA', uo_id=1, numero_livro=1, folhas_por_livro=100, numero_folha=1, numero_registro=1
            )
            configuracao.modalidades.add(11)

        lista = [
            ('Técnico em Geologia', 114),
            ('Técnico em Estradas', 108),
            ('Técnico em Edificações', 109),
            ('Técnico em Saneamento', 110),
            ('Técnico em Mecânica', 111),
            ('Técnico em Eletrônica', 112),
            ('Técnico em Mineração', 113),
        ]

        for nome_matriz, curso_campus in lista:
            matriz = Matriz.objects.get(nome=nome_matriz)
            Historico.objects.filter(aluno__curso_campus=curso_campus).update(matriz=matriz)

        Matriz.objects.update(
            carga_horaria=0,
            carga_horaria_estagio=850,
            reconhecimento='Curso aprovado  através da portaria nº 50, de 07 de julho de 1981 - Ministério da Educação e Cultura/Secretaria de Ensino de 1º e 2º graus, publicada no D.O.U., de 10 de julho de 1981, Seção I.',
        )
