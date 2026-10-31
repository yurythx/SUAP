import csv

from django.db.models import Q

from djtools.management.commands import BaseCommandPlus
from djtools.templatetags.filters.utils import format_datetime
from edu.models import Aluno, Modalidade, SituacaoMatricula
from rh.models import Servidor, Situacao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        publico = []
        cpfs = set()

        servidores = (
            Servidor.objects.filter(Q(eh_docente=True) | Q(eh_tecnico_administrativo=True))
            .filter(ativo=True)
            .filter(
                situacao__codigo__in=[
                    Situacao.ATIVO_PERMANENTE,
                    Situacao.CEDIDO_REQUISITADO,
                    Situacao.ATIVO_EM_OUTRO_ORGAO,
                    Situacao.COLABORADOR_ICT,
                    Situacao.COLABORADOR_PCCTAE,
                    Situacao.EXERCICIO_PROVISORIO,
                ]
            )
            .order_by('data_inicio_exercicio_na_instituicao')
            .values(
                'pessoa_fisica__cpf',
                'matricula',
                'pessoa_fisica__nome',
                'setor_lotacao__uo__sigla',
                'email_institucional',
                'data_inicio_exercicio_na_instituicao',
                'eh_docente',
                'email_siape',
                'situacao__nome_siape',
            )
        )
        for s in servidores:
            if s['pessoa_fisica__cpf'] in cpfs:
                continue

            perfil = 'tae'
            if s['eh_docente']:
                perfil = 'docente'

            email = s['email_institucional']
            if not email:
                email = s['email_siape']

            cpfs.add(s['pessoa_fisica__cpf'])
            publico.append(
                {
                    'cpf': s['pessoa_fisica__cpf'],
                    'matricula': s['matricula'],
                    'nome': s['pessoa_fisica__nome'],
                    'campus': s['setor_lotacao__uo__sigla'],
                    'email': email,
                    'datainicio': format_datetime(s['data_inicio_exercicio_na_instituicao']),
                    'perfil': perfil,
                    'situacao': s['situacao__nome_siape'],
                }
            )

        alunos = (
            Aluno.objects.filter(aluno_especial=False)
            .filter(situacao=SituacaoMatricula.MATRICULADO)
            .filter(matriz__isnull=False)
            .exclude(curso_campus__modalidade__pk=Modalidade.FIC)
            .order_by('data_matricula')
            .values(
                'pessoa_fisica__cpf',
                'matricula',
                'pessoa_fisica__nome',
                'curso_campus__diretoria__setor__uo__sigla',
                'email_academico',
                'data_matricula',
            )
        )
        for a in alunos:
            if a['pessoa_fisica__cpf'] in cpfs:
                continue

            email_aluno = a['email_academico']

            cpfs.add(a['pessoa_fisica__cpf'])
            publico.append(
                {
                    'cpf': a['pessoa_fisica__cpf'],
                    'matricula': a['matricula'],
                    'nome': a['pessoa_fisica__nome'].replace('\t', ' '),
                    'campus': a['curso_campus__diretoria__setor__uo__sigla'],
                    'email': email_aluno,
                    'datainicio': format_datetime(a['data_matricula'].date()),
                    'perfil': 'aluno',
                    'situacao': 'matriculado',
                }
            )

        rows_by_filename = {}
        for row in publico:
            filename = f'{row["campus"] or "SEMCAMPUS"}_{row["perfil"]}.csv'
            rows_by_filename.setdefault(filename, []).append(row)

        for filename, rows in rows_by_filename.items():
            with open(filename, 'w') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['cpf', 'matricula', 'nome', 'email', 'campus', 'datainicio', 'perfil', 'situacao'])
                writer.writeheader()
                for dic in rows:
                    writer.writerow(dic)
            self.stdout.write(f'Arquivo gerado: {filename}')
