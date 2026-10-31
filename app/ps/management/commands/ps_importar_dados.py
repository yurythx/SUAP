from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from djtools.utils import to_ascii
from ps.models import Inscricao, OfertaVaga

map = {}
map[to_ascii('Educação a Distância'.lower())] = 14
map[to_ascii('Apodi'.lower())] = 8
map[to_ascii('Ipanguaçu'.lower())] = 6
map[to_ascii('João Câmara'.lower())] = 9
map[to_ascii('Natal-Central'.lower())] = 1
map[to_ascii('Natal - Cidade Alta'.lower())] = 13
map[to_ascii('Natal-Zona Norte'.lower())] = 2
map[to_ascii('Nova Cruz'.lower())] = 16
map[to_ascii('Mossoró'.lower())] = 4
map[to_ascii('Parnamirim'.lower())] = 15
map[to_ascii('Santa Cruz'.lower())] = 12
map[to_ascii('São Gonçalo do Amarante'.lower())] = 17
map[to_ascii('Educação a Distância'.lower())] = 14
map[to_ascii('Macau'.lower())] = 10
map[to_ascii('Natal - Zona Norte'.lower())] = 2
map[to_ascii('Currais Novos'.lower())] = 3
map[to_ascii('Caicó'.lower())] = 7
map[to_ascii('Natal -Cidade Alta'.lower())] = 13
map[to_ascii('Natal - Zona Norte'.lower())] = 2
map[to_ascii('Natal - Central'.lower())] = 1
map[to_ascii('Pau dos Ferros'.lower())] = 11
map[to_ascii('Câmpus EaD'.lower())] = 14
map[to_ascii('Natal -  Central'.lower())] = 1
map[to_ascii('Natal - Cidade Alta'.lower())] = 13
map[to_ascii('Polo de Apodi'.lower())] = 14
map[to_ascii('Polo de Currais Novos'.lower())] = 14
map[to_ascii('Polo de João Câmara'.lower())] = 14
map[to_ascii('Polo de Macau'.lower())] = 14
map[to_ascii('Polo de Mossoró'.lower())] = 14
map[to_ascii('Polo de Parnamirim'.lower())] = 14
map[to_ascii('Polo de São Gonçalo do Amarante'.lower())] = 14
map[to_ascii('Polo de Caicó'.lower())] = 14
map[to_ascii('Polo de Caraúbas'.lower())] = 14
map[to_ascii('Polo de Cuité de Mamanguape'.lower())] = 14
map[to_ascii('Polo UAB de Caraúbas'.lower())] = 14
map[to_ascii('Polo UAB de Currais Novos'.lower())] = 14
map[to_ascii('Polo UAB de Guamaré'.lower())] = 14
map[to_ascii('Câmpus Educação a Distância'.lower())] = 14
map[to_ascii('Polo de Lajes'.lower())] = 14
map[to_ascii('Polo Zona Norte'.lower())] = 14
map[to_ascii('Polo de Assu'.lower())] = 14
map[to_ascii('Polo Grossos'.lower())] = 14
map[to_ascii('Polo de Guamaré'.lower())] = 14
map[to_ascii('CAMPUS NATAL CENTRAL'.lower())] = 1


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        count = 0
        Inscricao.objects.filter(ano=2013).delete()
        OfertaVaga.objects.filter(ano=2013).delete()
        print('INSCRITOS')
        f = open(settings.BASE_DIR + '/ps/arquivos/inscritos.txt')
        line = f.readline()
        line = f.readline()
        while line:
            count += 1
            token = line.strip().split('\t')
            ano, semestre, concurso, nivel, modalidade, unidade, curso, turno, numero, nome, cpf = (
                token[0],
                token[1],
                token[2],
                token[3],
                token[4],
                token[5],
                token[6],
                token[7],
                token[8],
                token[9],
                token[10],
            )
            uo_id = map[to_ascii(unidade.lower())]
            Inscricao.objects.create(
                unidade=unidade,
                concurso=concurso,
                curso=curso,
                turno=turno,
                numero=numero,
                cpf=cpf,
                candidato=nome,
                nivel=f'{nivel} ({modalidade})',
                ano=ano,
                semestre=semestre,
                uo_id=uo_id,
            )
            line = f.readline()
        print(count)
        f.close()
        print('VAGAS')
        f = open(settings.BASE_DIR + '/ps/arquivos/vagas.txt')
        line = f.readline()
        line = f.readline()
        count = 0
        while line:
            token = line.strip().split('\t')
            count += 1
            ano, semestre, concurso, unidade, curso, turno, qtd = token[0], token[1], token[2], token[3], token[4], token[5], token[6]
            uo_id = map[to_ascii(unidade.lower())]
            OfertaVaga.objects.create(unidade=unidade, concurso=concurso, curso=curso, turno=turno, qtd=qtd, ano=ano, semestre=semestre, uo_id=uo_id)
            line = f.readline()
        print(count)
        f.close()
