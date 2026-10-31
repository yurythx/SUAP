""" """

import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from random import choice

from django.conf import settings

from ae.models import Caracterizacao, HistoricoCaracterizacao
from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, ConfiguracaoAvaliacao, CursoCampus, MatriculaPeriodo
from edu.models.cadastros_gerais import CursoFormacaoSuperior, SituacaoMatricula, SituacaoMatriculaPeriodo
from edu.models.cursos import Componente
from edu.models.historico import AproveitamentoEstudo, CertificacaoConhecimento, MatriculaDiario, MatriculaDiarioResumida, RegistroHistorico
from edu.models.professores import Professor
from etep.models import AcompanhamentoEncaminhamento, Encaminhamento
from rh.models import Servidor, UnidadeOrganizacional

DIR_PATH = os.path.join(settings.BASE_DIR, 'dados')
if not os.path.exists(DIR_PATH):
    os.mkdir(DIR_PATH)


def progress_bar(i, total, description):
    percent = (i + 1) * 100 / total
    sys.stdout.write('\r')
    sys.stdout.write(f'[{"=" * int(percent / 2):<50}] {percent}% - {i + 1} de {total} {description}')
    sys.stdout.flush()
    if percent == 100:
        sys.stdout.write('')


def random(size=10, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'):
    """Returns a randomic string."""
    return ''.join([choice(allowed_chars) for i in range(size)])


def mask(i):
    return i * 2788132 + 918127201


def print_json(data, name, mode='w'):
    file_path = os.path.join(DIR_PATH, f'{name}.json')
    total = len(data)
    for i, item in enumerate(data):
        progress_bar(i, total, name.lower())
        for key in item:
            if isinstance(item[key], Decimal):
                item[key] = float(item[key])
            if type(item[key]) in (date, datetime):
                item[key] = item[key].strftime('%d/%m/%Y')
            elif item[key] and (key == 'id' or '_id' in key):
                item[key] = mask(item[key])

    file_content = '[{}]'.format(', '.join([json.dumps(x) for x in data]))
    # print '============== %s ==============\n%s\n\n' % (name, file_content)
    with open(file_path, mode) as f:
        f.write(file_content)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        cls = Caracterizacao
        fields = cls._meta.get_fields()
        for field in fields:
            if field.related_model and field.related_model not in (Aluno, HistoricoCaracterizacao):
                qs = field.related_model.objects
                print_json(list(qs.values()), qs.model.__name__)

        qs = UnidadeOrganizacional.objects.suap().all()
        print_json(qs.values('id', 'sigla'), qs.model.__name__)
        qs = Encaminhamento.objects.all()
        print_json(qs.values('id', 'descricao'), qs.model.__name__)
        qs = CursoCampus.objects.filter(ativo=True)
        print_json(qs.values('id', 'descricao_historico', 'diretoria__setor__uo_id'), qs.model.__name__)
        qs = SituacaoMatricula.objects.all()
        print_json(qs.values('id', 'descricao'), qs.model.__name__)
        qs = SituacaoMatriculaPeriodo.objects.all()
        print_json(qs.values('id', 'descricao'), qs.model.__name__)
        qs_alunos = Aluno.objects.filter(ano_letivo__ano__gte=2018, matriz__isnull=False, curso_campus__ativo=True, curso_campus__codigo='01404')  #
        print_json(
            qs_alunos.values(
                'id',
                'ano_letivo__ano',
                'periodo_letivo',
                'situacao_id',
                'curso_campus_id',
                'cep',
                'cidade__nome',
                'cidade__estado__nome',
                'pessoa_fisica__nascimento_data',
                'pessoa_fisica__sexo',
            ),
            qs_alunos.model.__name__,
        )
        qs = Caracterizacao.objects.filter(aluno__in=qs_alunos.filter(caracterizacao__isnull=False).values_list('id', flat=True))
        print_json(list(qs.values()), qs.model.__name__)
        qs = AcompanhamentoEncaminhamento.objects.filter(acompanhamento__aluno__in=qs_alunos.values_list('id', flat=True))
        print_json(qs.values('id', 'acompanhamento__aluno_id', 'data', 'encaminhamento_id'), qs.model.__name__)
        qs_matriculas_periodo = MatriculaPeriodo.objects.filter(aluno__in=qs_alunos.values_list('id', flat=True))
        print_json(
            qs_matriculas_periodo.values('id', 'aluno_id', 'situacao_id', 'ano_letivo__ano', 'periodo_letivo'), qs_matriculas_periodo.model.__name__
        )
        situacoes_diciplina = []
        for chave, valor in MatriculaDiario.SITUACAO_CHOICES:
            situacoes_diciplina.append({'id': chave, 'descricao': valor})
        print_json(situacoes_diciplina, 'SituacaoDisciplina')

        notas = []
        qs_matriculas_diarios = MatriculaDiario.objects.exclude(situacao=1).filter(
            matricula_periodo__in=qs_matriculas_periodo.values_list('id', flat=True)
        )
        total = qs_matriculas_diarios.count()
        for i, md in enumerate(qs_matriculas_diarios):
            progress_bar(i, total, 'matrículas em diário')
            etapas = []
            if md.diario.componente_curricular.qtd_avaliacoes:
                for etapa in [*list(range(1, md.diario.componente_curricular.qtd_avaliacoes + 1)), 5]:
                    notas_etapa = []
                    for nota_etapa in md.get_notas_etapa(etapa):
                        notas_etapa.append({'item_configuracao_avaliacao_id': nota_etapa.item_configuracao_avaliacao_id, 'nota': nota_etapa.nota})
                        configuracao_avaliacao = getattr(md.diario, f'configuracao_avaliacao_{etapa}')()
                    etapas.append(
                        {
                            'etapa': str(etapa),
                            'media': getattr(md, 'nota_{}'.format(etapa == 5 and 'final' or etapa)),
                            'notas': notas_etapa,
                            'qtd_faltas': md.get_numero_faltas(etapa),
                            'configuracao_avaliacao_id': configuracao_avaliacao.id,
                        }
                    )
            notas.append(
                {
                    'matricula_periodo_id': md.matricula_periodo.pk,
                    'situacao_id': md.situacao,
                    'media_final': float(md.get_media_final_disciplina() or 0),
                    'percentual_frequencia': md.get_percentual_carga_horaria_frequentada(),
                    'disciplina_id': md.diario.componente_curricular.componente.pk,
                    'professores': [mask(x) for x in md.diario.professordiario_set.values_list('professor', flat=True)],
                    'etapas': etapas,
                }
            )
        qs_matriculas_diarios_resumida = MatriculaDiarioResumida.objects.exclude(equivalencia_componente__componente__isnull=True).filter(
            matricula_periodo__in=qs_matriculas_periodo.values_list('id', flat=True)
        )
        total = qs_matriculas_diarios_resumida.count()
        for i, md in enumerate(qs_matriculas_diarios_resumida):
            progress_bar(i, total, 'matrículas em diário (resumida)')
            notas.append(
                {
                    'matricula_periodo_id': md.matricula_periodo.pk,
                    'situacao_id': md.situacao,
                    'media_final': float(md.media_final_disciplina or 0),
                    'percentual_frequencia': md.frequencia,
                    'disciplina_id': md.equivalencia_componente.componente.pk,
                }
            )
        qs_registros_historico = RegistroHistorico.objects.filter(matricula_periodo__in=qs_matriculas_periodo.values_list('id', flat=True))
        total = qs_registros_historico.count()
        for i, md in enumerate(qs_registros_historico):
            progress_bar(i, total, 'registros de histórico')
            notas.append(
                {
                    'matricula_periodo_id': md.matricula_periodo.pk,
                    'situacao_id': md.situacao,
                    'media_final': float(md.media_final_disciplina or 0),
                    'percentual_frequencia': md.frequencia,
                    'disciplina_id': md.componente.pk,
                }
            )
        qs_aproveitamentos_estudo = AproveitamentoEstudo.objects.filter(matricula_periodo__in=qs_matriculas_periodo.values_list('id', flat=True))
        total = qs_aproveitamentos_estudo.count()
        for i, md in enumerate(qs_aproveitamentos_estudo):
            progress_bar(i, total, 'aproveitamentos')
            notas.append(
                {
                    'matricula_periodo_id': md.matricula_periodo.pk,
                    'situacao_id': md.nota and md.nota > 59 and 2 or 3,
                    'media_final': float(md.nota or 0),
                    'percentual_frequencia': md.frequencia,
                    'disciplina_id': md.componente_curricular.componente.pk,
                }
            )
        qs_certificacao_conhecimento = CertificacaoConhecimento.objects.filter(
            matricula_periodo__in=qs_matriculas_periodo.values_list('id', flat=True)
        )
        total = qs_certificacao_conhecimento.count()
        for i, md in enumerate(qs_certificacao_conhecimento):
            progress_bar(i, total, 'certificações')
            notas.append(
                {
                    'matricula_periodo_id': md.matricula_periodo.pk,
                    'situacao_id': md.nota and md.nota > 59 and 2 or 3,
                    'media_final': float(md.nota or 0),
                    'percentual_frequencia': None,
                    'disciplina_id': md.componente_curricular.componente.pk,
                }
            )

        id_disciplinas = list(
            qs_matriculas_diarios.order_by('diario__componente_curricular__componente')
            .values_list('diario__componente_curricular__componente', flat=True)
            .distinct()
        )
        id_disciplinas.extend(
            list(
                qs_matriculas_diarios_resumida.exclude(equivalencia_componente__componente__isnull=True)
                .order_by('equivalencia_componente__componente')
                .values_list('equivalencia_componente__componente', flat=True)
                .distinct()
            )
        )
        id_disciplinas.extend(
            list(qs_registros_historico.order_by('componente').values_list('componente', flat=True).distinct()),
        )
        id_disciplinas.extend(
            list(
                qs_aproveitamentos_estudo.order_by('componente_curricular__componente')
                .values_list('componente_curricular__componente', flat=True)
                .distinct()
            )
        )
        id_disciplinas.extend(
            list(
                qs_certificacao_conhecimento.order_by('componente_curricular__componente')
                .values_list('componente_curricular__componente', flat=True)
                .distinct()
            )
        )
        id_disciplinas.extend(
            list(
                qs_certificacao_conhecimento.order_by('componente_curricular__componente')
                .values_list('componente_curricular__componente', flat=True)
                .distinct()
            )
        )
        qs_disciplinas = Componente.objects.filter(pk__in=set(id_disciplinas))
        print_json(qs_disciplinas.values('id', 'descricao_historico', 'ch_hora_relogio'), 'Disciplina')

        professores = []
        qs_professores = Professor.objects.filter(
            pk__in=qs_matriculas_diarios.values_list('diario__professordiario__professor').order_by('diario__professordiario__professor').distinct()
        )

        qs_curso_formacao_superior = CursoFormacaoSuperior.objects.filter(
            codigo__in=qs_professores.values_list('codigo_curso_superior').order_by('codigo_curso_superior').distinct()
        )
        print_json(qs_curso_formacao_superior.values('codigo', 'descricao', 'grau'), 'CursoFormacaoSuperior')
        total = qs_professores.count()
        for i, professor in enumerate(qs_professores):
            progress_bar(i, total, 'professores')
            registro = {}
            registro['id'] = professor.pk
            registro['titulacao'] = professor.titulacao
            qs_servidor = Servidor.objects.filter(pessoa_fisica__pk=professor.vinculo.pessoa.pk)
            if qs_servidor.exists():
                servidor = qs_servidor[0]
                registro['data_ingresso'] = servidor.data_inicio_exercicio_na_instituicao
                registro['regime'] = servidor.jornada_trabalho.nome
            else:
                registro['data_ingresso'] = None
                registro['regime'] = None
            registro['codigo_curso_formacao_superior'] = professor.codigo_curso_superior
            professores.append(registro)
        print_json(professores, 'Professores')
        print_json(notas, 'Notas')

        configuracoes_avaliacao = []
        qs_configuracoes_avaliacao = ConfiguracaoAvaliacao.objects.filter(
            diario__in=qs_matriculas_diarios.values_list('diario', flat=True).order_by('diario').distinct()
        )
        total = qs_configuracoes_avaliacao.count()
        for i, c in enumerate(qs_configuracoes_avaliacao):
            progress_bar(i, total, 'configurações de avaliação')
            registro = {
                'id': c.pk,
                'forma_calculo': c.get_forma_calculo_display(),
                'divisor': c.divisor,
                'maior_nota': c.maior_nota,
                'menor_nota': c.menor_nota,
                'itens': [],
            }
            for item in c.itemconfiguracaoavaliacao_set.all():
                registro['itens'].append(
                    {
                        'id': item.pk,
                        'tipo': item.get_tipo_display(),
                        'sigla': item.sigla,
                        'descricao': item.descricao,
                        'data': item.data and item.data.strftime('%d/%m/%Y') or None,
                        'nota_maxima': item.nota_maxima,
                        'peso': item.peso,
                    }
                )
            configuracoes_avaliacao.append(registro)
        print_json(configuracoes_avaliacao, 'ConfiguracoesAvaliacao')

        self.stdout.write(f'Files saved at {DIR_PATH}/!')
