import datetime
import os

from django.conf import settings

from comum.models import Configuracao
from djtools.utils import to_ascii
from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import Cidade, Deficiencia, Estado, Modalidade, SituacaoMatricula, SituacaoMatriculaPeriodo, TipoNEE
from edu.models.cursos import ComponenteCurricular
from edu.models.diarios import ProfessorDiario
from edu.models.diretorias import CalendarioAcademico, Diretoria
from edu.models.professores import Professor
from edu.models.turmas import Turma
from rh.models import Servidor, UnidadeOrganizacional
from rh.enums import Nacionalidade

MODALIDADES = (
    Modalidade.INTEGRADO,
    Modalidade.SUBSEQUENTE,
    Modalidade.INTEGRADO_EJA,
    Modalidade.FIC_INTEGRADO_EJA,
    Modalidade.PROEJA_FIC_FUNDAMENTAL,
    Modalidade.CONCOMITANTE,
)
MODALIDADES_PARTIUIF = (Modalidade.FIC,)


def formatar(texto, remover_virgula=False):
    if texto is None:
        texto = ''
    for caractere in ("'", '"', '-', '.', 'ª', 'º', ':', '&', ')', '(', '*', '=', ';', ':', '+', ']', '[', '}', '{'):
        texto = texto.replace(caractere, '')
    if remover_virgula:
        texto = texto.replace(',', '')
    texto = texto.replace('  ', ' ')
    return to_ascii(texto).upper()


class ExportadorAlunosSemCodigo:
    def __init__(self, ano, task):
        self.ano = ano
        self.registros = []

        pks = (
            Turma.objects.filter(
                curso_campus__modalidade__in=MODALIDADES,
                # curso_campus__programa='PartiuIF',
                ano_letivo__ano=self.ano,
                diario__matriculadiario__isnull=False,
                diario__matriculadiario__matricula_periodo__aluno__codigo_educacenso__isnull=True,
            )
            .values_list('diario__matriculadiario__matricula_periodo__aluno', flat=True)
            .order_by('diario__matriculadiario__matricula_periodo__aluno')
            .distinct()
        )
        alunos = Aluno.objects.filter(pk__in=pks)
        alunos = alunos.exclude(naturalidade__isnull=True)

        for aluno in task.iterate(alunos):
            if aluno.pessoa_fisica.cpf:
                cpf_aluno = str(aluno.pessoa_fisica.cpf).replace('.', '').replace('-', '')
                cpf_aluno = str(int(cpf_aluno))
                cpf_aluno = cpf_aluno.rjust(11, '0')
            else:
                cpf_aluno = '00000000000'
            if aluno.nacionalidade == 'Brasileira':
                codigo_ibge = aluno.naturalidade_id and aluno.naturalidade.codigo or ''
            else:
                codigo_ibge = aluno.curso_campus.diretoria.setor.uo.municipio.codigo
            self.registros.append(
                '{}|{}||{}|{}|{}|{}|{}|'.format(
                    aluno.matricula,
                    cpf_aluno,
                    formatar(aluno.pessoa_fisica.nome),
                    aluno.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y'),
                    formatar(aluno.nome_mae or aluno.pessoa_fisica.nome_mae or ''),
                    formatar(aluno.nome_pai or aluno.pessoa_fisica.nome_pai or ''),
                    codigo_ibge,
                )
            )
        file_path = os.path.join(settings.TEMP_DIR, 'alunos_sem_codigo.txt')
        f = open(file_path, 'w')
        f.write(str('\r\n'.join(self.registros)))
        f.close()
        task.finalize('Arquivo gerado com sucesso', '/', file_path=file_path)


class Exportador:
    DOCENTE = 1
    ALUNOS = 2

    ETAPAS_MEDIO = [25, 26, 27, 28, 29]
    ETAPAS_EJA = [67, 74]
    ETAPAS_TECNICO = [39, 40, 64, 68, 75]

    def __init__(self, ano, uo, validar_alunos, ignorar_erros, ignorar_matriculas, filtrar_matriculas, inferir_turma, partiu_if, task):
        self.ano = ano
        self.inferir_turma = inferir_turma
        self.partiu_if = partiu_if

        self.registros = []
        self.cpf_operador = task.user and task.user.get_profile().cpf or None
        self.modalidades = MODALIDADES_PARTIUIF if partiu_if else MODALIDADES

        self.erros = []
        dados = []

        # data corte é última quarta feira de maio
        primeiro_dia_junho = datetime.datetime(self.ano, 6, 1)
        data_corte = primeiro_dia_junho - datetime.timedelta(days=1)
        while data_corte.weekday() != 2:
            data_corte -= datetime.timedelta(days=1)

        alunos = Aluno.objects.filter(
            curso_campus__modalidade__in=self.modalidades,
            matriculaperiodo__ano_letivo__ano=self.ano,
            matriculaperiodo__periodo_letivo=1,
            curso_campus__diretoria__setor__uo_id=uo.id,
        )
        if partiu_if:
            alunos = alunos.filter(curso_campus__programa='PartiuIF')

        # retira matriculados após data de corte
        alunos = alunos.exclude(data_matricula__gt=data_corte.date())

        # retira transferidos internos
        alunos = alunos.exclude(situacao=SituacaoMatricula.TRANSFERIDO_INTERNO)

        # retira alunos formados antes da data de corte
        alunos = alunos.exclude(situacao_id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO], dt_conclusao_curso__lt=data_corte.date())

        # retira alunos inativos antes da data de corte
        ids_alunos_remover = []
        for aluno in alunos.filter(
            situacao_id__in=[
                SituacaoMatricula.JUBILADO,
                SituacaoMatricula.EVASAO,
                SituacaoMatricula.CANCELADO,
                SituacaoMatricula.TRANSFERIDO_EXTERNO,
                SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
                SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
                SituacaoMatricula.TRANCADO,
                SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
                SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO,
            ]
        ).only('id'):
            data = aluno.get_data_ultimo_procedimento_periodo_referencia()
            if data and data < data_corte.date():
                ids_alunos_remover.append(aluno.id)
        alunos = alunos.exclude(id__in=ids_alunos_remover)

        if ignorar_matriculas and ignorar_matriculas[0] != '':
            alunos = alunos.exclude(matricula__in=ignorar_matriculas)

        if filtrar_matriculas and filtrar_matriculas[0] != '':
            alunos = alunos.filter(matricula__in=filtrar_matriculas)

        alunos = alunos.order_by('pessoa_fisica__cpf').order_by('-matriculaperiodo').distinct()
        alunos_final = set()
        ids_turmas = set()
        for aluno in alunos:
            apto, turma, nacionalidade, codigo_educacenso_indigena = self.check_aluno(aluno)
            if apto:
                aluno.turma = turma
                aluno.codigo_educacenso_nacionalidade = nacionalidade
                aluno.codigo_educacenso_indigena = codigo_educacenso_indigena
                alunos_final.add(aluno)
                ids_turmas.add(turma.id)

        # antecipa geração de relatório de erros com dados de alunos
        file_path = os.path.join(settings.TEMP_DIR, 'educacenso_validacao_aluno.txt')
        if validar_alunos and self.erros:
            s = '\r\n'.join(self.erros)
            with open(file_path, 'w') as f:
                f.write(s)
            task.finalize('Arquivo gerado com sucesso', '/edu/relatorio_educacenso/', file_path=file_path)
        else:
            ids_servidores = ProfessorDiario.objects.filter(
                diario__turma_id__in=ids_turmas,
                diario__matriculadiario__isnull=False,
                professor__vinculo__tipo_relacionamento__model='servidor',
            ).values_list('professor__vinculo__id_relacionamento', flat=True)

            turmas = Turma.objects.filter(id__in=ids_turmas)
            professores = Servidor.objects.filter(eh_docente=True, pk__in=ids_servidores).distinct()
            dados.append((alunos_final, turmas, professores))

            for alunos, turmas, professores in dados:
                task.count(turmas, alunos, alunos, professores, professores)

            for alunos, turmas, professores in dados:
                self.exportar_registros_00(uo)
                self.exportar_registros_10(uo)
                self.exportar_registros_20(turmas, task)
                self.exportar_registros_30(professores, turmas, None, task)
                self.exportar_registros_30_alunos(alunos, task)
                self.exportar_registros_40(turmas, uo, task)
                self.exportar_registros_50(professores, turmas, task)
                self.exportar_registros_60(alunos, task)
                self.registros.append('99|')

                file_path = os.path.join(settings.TEMP_DIR, 'educacenso.txt')
                if ignorar_erros or not self.erros:
                    s = '\r\n'.join(self.registros)
                else:
                    s = '\r\n'.join(self.erros)
                with open(file_path, 'w') as f:
                    f.write(s)
                task.finalize('Arquivo gerado com sucesso', '/edu/relatorio_educacenso/', file_path=file_path)

    def adicionar(self, registro):
        for i, item in enumerate(registro):
            registro[i] = str(item)
        self.registros.append('|'.join(registro))

    def exportar_registros_00(self, uo):
        siglas = uo.sigla == 'EAD' and (uo.sigla, 'CNAT') or (uo.sigla,)
        diretoria = Diretoria.objects.filter(setor__uo__sigla__in=siglas).first()
        if diretoria:
            calendario_academico = CalendarioAcademico.objects.filter(
                eh_calendario_referencia=True,
                diario__turma__curso_campus__diretoria__setor__uo=uo,
                diario__ano_letivo__ano=self.ano,
            ).first()
            data_inicio = None
            data_fim = None
            if calendario_academico is None:
                qs_calendario_academico = CalendarioAcademico.objects.exclude(descricao__unaccent__icontains='depend').filter(
                    diario__turma__curso_campus__diretoria__setor__uo=uo,
                    diario__turma__curso_campus__modalidade__in=self.modalidades,
                    diario__ano_letivo__ano=self.ano,
                )
                if self.partiu_if:
                    qs_calendario_academico = qs_calendario_academico.filter(diario__turma__curso_campus__programa='PartiuIF')

                if qs_calendario_academico.exists():
                    from django.db.models import Max, Min

                    inicio = qs_calendario_academico.aggregate(Min('data_inicio'))
                    data_inicio = inicio and inicio['data_inicio__min'] and inicio['data_inicio__min'].strftime('%d/%m/%Y')
                    fim = qs_calendario_academico.aggregate(Max('data_fim'))
                    data_fim = fim and fim['data_fim__max'] and fim['data_fim__max'].strftime('%d/%m/%Y')
            else:
                data_inicio = calendario_academico.data_inicio.strftime('%d/%m/%Y')
                data_fim = calendario_academico.data_fim.strftime('%d/%m/%Y')

            if data_inicio and data_fim:
                if diretoria.diretor_geral_id:
                    registro = []
                    # 1 Tipo de registro
                    registro.append('00')
                    # 2 Código de escola - Inep
                    registro.append(uo.codigo_inep)
                    # 3 Situação de funcionamento
                    registro.append(1)
                    # 4 Data de início do ano letivo
                    registro.append(data_inicio)
                    # 5 Data de término do ano letivo
                    registro.append(data_fim)
                    # 6 Nome da escola
                    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
                    registro.append(f'{instituicao} - {to_ascii(diretoria.setor.uo.nome).upper()}')
                    # 7 CEP
                    registro.append(formatar(diretoria.setor.uo.cep))
                    # 8 Município
                    estado = Estado.objects.get(pk=Estado.ESTADOS[diretoria.setor.uo.municipio.uf])
                    qs_cidade = Cidade.objects.filter(nome=diretoria.setor.uo.municipio.nome.upper(), estado=estado)
                    registro.append(qs_cidade.exists() and qs_cidade[0].codigo or diretoria.setor.uo.municipio.codigo)
                    # 9 Distrito
                    registro.append('05')
                    # 10 Endereço
                    registro.append(formatar(diretoria.setor.uo.endereco))
                    # 11 Endereço número
                    registro.append('')
                    # 12 Complemento
                    registro.append('')
                    # 13 Bairro
                    registro.append('')
                    # 14 DDD
                    registro.append('')
                    # 15 Telefone
                    registro.append('')
                    # 16 Outro telefone de contato
                    registro.append('')
                    # 17 Endereço eletrônico (e-mail) da escola
                    registro.append('')
                    # 18 Código do órgão regional de ensino
                    registro.append('')
                    # 19 Localização/Zona da escola
                    registro.append(diretoria.setor.uo.zona_rual and 2 or 1)
                    # 20 Localização diferenciada da escola
                    # 1 - Área de assentamento
                    # 2 - Terra indígena
                    # 3 - Comunidade quilombola
                    # 7 - Não está em área de localização diferenciada
                    # 8 - Área onde se localiza povos e comunidades tradicionais
                    registro.append(7)
                    # 21 Dependência administrativa
                    registro.append(1)
                    # 22 Secretaria de Educação/Ministério da Educação
                    registro.append(1)
                    # 23 Secretaria de Segurança Pública/Forças Armadas/Militar
                    registro.append(0)
                    # 24 Secretaria da Saúde/Ministério da Saúde
                    registro.append(0)
                    # 25 Outro órgão da administração pública
                    registro.append(0)
                    # 26 Mantenedora da escola privada - Empresa, grupos empresariais do setor privado ou pessoa física.
                    registro.append('')
                    # 27 Mantenedora da escola privada - Sindicatos de trabalhadores ou patronais, associações, cooperativas.
                    registro.append('')
                    # 28 Mantenedora da escola privada - Organização não governamental (ONG) - nacional ou internacional.
                    registro.append('')
                    # 29 Mantenedora da escola privada - Instituições sem fins lucrativos.
                    registro.append('')
                    # 30 Mantenedora da escola privada - Sistema S (Sesi, Senai, Sesc, outros)
                    registro.append('')
                    # 31 Mantenedora da escola privada - Organização da Sociedade Civil de Interesse Público (Oscip)
                    registro.append('')
                    # 32 Categoria da escola privada
                    registro.append('')
                    # 33 Secretaria Estadual como poder público responsável pela parceria ou convênio entre a Administração Pública e outras instituições
                    registro.append(0)
                    # 34 Secretaria Municipal como poder público responsável pela parceria ou convênio entre a Administração Pública e outras instituições
                    registro.append(0)

                    # 35 a 40 Forma(s) de contratação da parceria ou convênio entre a escola e a Secretaria Estadual de Educação
                    # 35 Termo de colaboração (Lei nº 13.019/2014)
                    registro.append('')
                    # 36 Termo de fomento (Lei nº 13.019/2014)
                    registro.append('')
                    # 37 Acordo de cooperação (Lei nº 13.019/2014)
                    registro.append('')
                    # 38 Contrato de prestação de serviço
                    registro.append('')
                    # 39 Termo de cooperação técnica e financeira
                    registro.append('')
                    # 40 Contrato de consórcio público/Convênio de cooperação
                    registro.append('')

                    # 41 a 46 Forma(s) de contratação da parceria ou convênio entre a escola e a Secretaria Municipal de Educação
                    # 41 Termo de colaboração (Lei nº 13.019/2014)
                    registro.append('')
                    # 42 Termo de fomento (Lei nº 13.019/2014)
                    registro.append('')
                    # 43 Acordo de cooperação (Lei nº 13.019/2014)
                    registro.append('')
                    # 44 Contrato de prestação de serviço
                    registro.append('')
                    # 45 Termo de cooperação técnica e financeira
                    registro.append('')
                    # 46 Contrato de consórcio público/Convênio de cooperação
                    registro.append('')

                    # 47 CNPJ da mantenedora principal da escola privada
                    registro.append('')
                    # 48 Número do CNPJ da escola privada
                    registro.append('')
                    # 49 Regulamentação/Autorização no conselho ou órgão municipal, estadual ou federal de educação.
                    registro.append(1)
                    # 50 Esfera administrativa do conselho ou órgão responsável pela regulamentação/ autorização
                    # 1-Federal
                    # 2-Estadual
                    # 3-Municipal
                    # 4-Estadual e Municipal
                    # 5-Federal e Estadual
                    registro.append(1)
                    # 51 Unidade vinculada a Escola de Educação Básica ou Unidade ofertante de Ensino Superior
                    registro.append(uo.codigo_censup and 2 or 0)
                    # 52 Código da Escola Sede
                    registro.append('')
                    # 53 Código da IES
                    registro.append(uo.codigo_censup and '1082' or '')
                    self.adicionar(registro)

    def exportar_registros_10(self, uo):
        registro = []
        from edu.models import RespostaEducacenso

        qs = RespostaEducacenso.objects.filter(questao__registro__ano_censo__ano=self.ano, campus=uo).order_by('questao__numero_campo')
        for r in qs:
            if r.resposta == 'True':
                v = '1'
            elif r.resposta == 'False':
                v = '0'
            else:
                v = r.resposta or ''
            registro.append(v)
        self.adicionar(registro)

    def exportar_registros_20(self, turmas, task):
        for turma in task.iterate(turmas):
            diarios_turma = self.get_diarios_turma(turma)
            if diarios_turma.exists():
                curso = turma.curso_campus
                programa_partiuIf = curso.programa == 'PartiuIF'
                etapa_agregada, etapa = self.get_etapa(turma) if not programa_partiuIf else ('', '')
                if curso.curso_tecnico is None and (etapa_agregada in [304, 305] or etapa in [39, 40, 64, 74]):
                    self.erros.append(f'{curso.codigo}\t{curso.descricao}\tSEM CURSO TÉCNICO')
                    continue
                if etapa == 68 and curso.eixo is None:
                    self.erros.append(f'{curso.codigo}\t{curso.descricao}\tSEM EIXO TECNOLÓGICO')
                    continue
                registro = []
                # 1 Tipo de registro
                registro.append(20)
                # 2 Código de escola - Inep
                registro.append(curso.diretoria.setor.uo.codigo_inep)
                # 3 Código da Turma na Entidade/Escola
                codigo_turma = turma.codigo.replace('.', '')
                registro.append(codigo_turma)
                # 4 Código da Turma - INEP
                registro.append('')
                # 5 Nome da Turma
                # máximo de 80 caracteres
                registro.append(f'{formatar(curso.descricao_historico.strip()[0:62], True)} {codigo_turma}')
                # 6 Tipo de mediação didático-pedagógica
                # 1 - presencial
                # 2 - Semipresencial
                # 3 - Educaçaão a distancia
                is_presencial = not curso.diretoria.ead
                registro.append(is_presencial and 1 or 3)
                # 7 a 13 Dias da semana e horários de funcionamento da turma
                if is_presencial:
                    horario_aula = turma.diario_set.all()[0].horario_campus.horarioaula_set.filter(turno=turma.turno).order_by('numero')
                    if horario_aula.exists():
                        inicio = horario_aula.first().inicio
                        termino = horario_aula.last().termino
                        horario = f'{inicio}-{termino}'
                    else:
                        horario = '00:00-00:00'
                # 7 Domingo
                registro.append('')
                # 8 Segunda-feira
                registro.append(horario if is_presencial else '')
                # 9 Terça-feira
                registro.append(horario if is_presencial else '')
                # 10 Quarta-feira
                registro.append(horario if is_presencial else '')
                # 11 Quinta-feira
                registro.append(horario if is_presencial else '')
                # 12 Sexta-feira
                registro.append(horario if is_presencial else '')
                # 13 Sábado
                registro.append('')

                # 14 Tipo de turma
                # 4-Atividade complementar
                # 5-Atendimento educacional especializado (AEE)
                # 6-Curricular (etapa de ensino)
                # 9-Curricular (etapa de ensino) com Atividade Complementar
                registro.append(4 if programa_partiuIf else 6)

                # 15 a 20 Tipo de atividade complementar
                # 15 Código 1
                registro.append(31001 if is_presencial and programa_partiuIf else '')  # 31001 Matemática
                # 16 Código 2
                registro.append(31016 if is_presencial and programa_partiuIf else '')  # 31016 Linguagens
                # 17 Código 3
                registro.append(31017 if is_presencial and programa_partiuIf else '')  # 31017 Ciências da Natureza
                # 18 Código 4
                registro.append(31018 if is_presencial and programa_partiuIf else '')  # 31018 Ciências Humanas e Sociais
                # 19 Código 5
                registro.append('')
                # 20 Código 6
                registro.append('')
                # 21 Local de funcionamento diferenciado da turma
                registro.append('0')
                # 22 Turma de Educação Especial (classe especial)
                registro.append('' if programa_partiuIf else '0')
                # 23 Etapa agregada
                registro.append(etapa_agregada)
                # 24 Etapa
                registro.append(etapa)
                # 25 Código do eixo do curso de qualificação profissional [novo em 2026]
                registro.append(f'{curso.eixo.codigo_inep}000' if etapa == 68 else '')
                # 26 Código do curso
                registro.append(curso.curso_tecnico.codigo_inep if etapa in [39, 40, 64, 74] else '')
                # 27 Carga horária total do curso (em horas) [novo em 2026]
                registro.append(turma.matriz.get_carga_horaria_total_prevista() if etapa_agregada in [304, 305] else '')
                # 28 Formas de organização da turma
                # 1-Série/Ano (séries anuais)
                # 2-Períodos semestrais
                # 3-Ciclo(s)
                # 4-Grupos não seriados com base na idade ou competência
                # 5-Módulos
                if programa_partiuIf:
                    registro.append('')
                else:
                    registro.append('2' if etapa in [68, 40] else '1')

                # 29 Turma de Formação por Alternância (proposta pedagógica de formação por alternância: tempo-escola e tempo-comunidade)
                registro.append('0')

                # 30 a 32 Organização curricular da turma
                # 30 Formação geral básica (FGB)
                registro.append('1' if etapa_agregada in [304, 305] else '')
                # 31 Itinerário formativo de aprofundamento (IFA)
                registro.append('0' if etapa_agregada in [304, 305] else '')
                # 32 Itinerário de formação técnica e profissional (IFTP)
                registro.append('1' if etapa_agregada in [304, 305] else '')

                # 33 a 36 Área(s) do itinerário formativo
                # 33 Linguagens e suas tecnologias
                registro.append('')
                # 34 Matemática e suas tecnologias
                registro.append('')
                # 35 Ciências da natureza e suas tecnologias
                registro.append('')
                # 36 Ciências humanas e sociais aplicadas
                registro.append('')

                # 37 Tipo do curso do itinerário de formação técnica e profissional
                registro.append('1' if etapa_agregada in [304, 305] else '')
                # 38 Código do curso técnico
                registro.append(curso.curso_tecnico.codigo_inep if etapa_agregada in [304, 305] else '')

                # 39 a 65 Áreas do conhecimento/componentes curriculares
                if not etapa:
                    for _i in range(27):
                        registro.append('')
                else:
                    # 39 1 - Química
                    possui_quimica = self.possui_disciplina_quimica(diarios_turma, etapa)
                    registro.append('1' if possui_quimica else '0')

                    # 40 2 - Física
                    possui_fisica = self.possui_disciplina_fisica(diarios_turma, etapa)
                    registro.append('1' if possui_fisica else '0')

                    # 41 3 - Matemática
                    possui_matematica = self.possui_disciplina_matematica(diarios_turma, etapa)
                    registro.append('1' if possui_matematica else '0')

                    # 42 4 - Biologia
                    possui_biologia = self.possui_disciplina_biologia(diarios_turma, etapa)
                    registro.append('1' if possui_biologia else '0')

                    # 43 5 - Ciências
                    registro.append('0')

                    # 44 6 - Língua / Literatura portuguesa
                    possui_portugues = self.possui_disciplina_portugues(diarios_turma, etapa)
                    registro.append('1' if possui_portugues else '0')

                    # 45 7 - Língua / Literatura estrangeira - Inglês
                    possui_ingles = self.possui_disciplina_ingles(diarios_turma, etapa)
                    registro.append('1' if possui_ingles else '0')

                    # 46 8 - Língua / Literatura estrangeira - Espanhol
                    possui_espanhol = self.possui_disciplina_espanhol(diarios_turma, etapa)
                    registro.append('1' if possui_espanhol else '0')

                    # 47 9 - Língua / Literatura estrangeira - Outra
                    registro.append('0')

                    # 48 10 - Artes (educação artística, teatro, dança, música, artes plásticas e outras)
                    possui_artes = self.possui_disciplina_artes(diarios_turma, etapa)
                    registro.append('1' if possui_artes else '0')

                    # 49 11 - Educação física
                    possui_ed_fisica = self.possui_disciplina_educacao_fisica(diarios_turma, etapa)
                    registro.append('1' if possui_ed_fisica else '0')

                    # 50 12 - História
                    possui_historia = self.possui_disciplina_historia(diarios_turma, etapa)
                    registro.append('1' if possui_historia else '0')

                    # 51 13 - Geografia
                    possui_geografia = self.possui_disciplina_geografia(diarios_turma, etapa)
                    registro.append('1' if possui_geografia else '0')

                    # 52 14 - Filosofia
                    possui_filosofia = self.possui_disciplina_filosofia(diarios_turma, etapa)
                    registro.append('1' if possui_filosofia else '0')

                    # 53 16 - Informática/Computação
                    possui_informatica = self.possui_disciplina_informatica(diarios_turma, etapa)
                    registro.append('1' if possui_informatica else '0')

                    # 54 17 - Áreas do conhecimento profissionalizantes
                    possui_profissionalizante = self.possui_disciplina_profissionalizante(diarios_turma, etapa)
                    registro.append('1' if possui_profissionalizante else '0')

                    # 55 23 - Libras
                    possui_libras = self.possui_disciplina_libras(diarios_turma, etapa)
                    registro.append('1' if possui_libras else '0')

                    # 56 25 - 25. Áreas do conhecimento pedagógicas
                    registro.append('0')

                    # 57 26 - Ensino religioso
                    registro.append('0')

                    # 58 27 - Língua indígena
                    registro.append('0')

                    # 59 28 - Estudos sociais
                    registro.append('0')

                    # 60 29 - Sociologia
                    possui_sociologia = self.possui_disciplina_sociologia(diarios_turma, etapa)
                    registro.append('1' if possui_sociologia else '0')

                    # 61 30 - Língua / Literatura estrangeira - Francês
                    possui_frances = self.possui_disciplina_frances(diarios_turma, etapa)
                    registro.append('1' if possui_frances else '0')

                    # 62 31. Língua Portuguesa como Segunda Língua
                    registro.append('0')

                    # 63 32. Estágio curricular supervisionado
                    registro.append('0')

                    # 64 33. Projeto de vida
                    registro.append('0')

                    # 65 99. Outras áreas do conhecimento
                    possui_outras_areas = self.possui_outras_disciplinas(diarios_turma, etapa)
                    registro.append('1' if possui_outras_areas else '0')

                # 66 Turma de Educação Bilíngue de Surdos (classe bilíngue de surdos)
                registro.append(0)
                self.adicionar(registro)

    def exportar_registros_30(self, professores, turmas, uo, task):
        for servidor in task.iterate(professores):
            tem_erro, naturalidade, nacionalidade = self.check_servidor(servidor)
            if tem_erro:
                continue

            if turmas:
                turmas_professor = self.get_turmas_professor(servidor, turmas)
                if not turmas_professor:
                    continue
                if uo is None:
                    uo = turmas_professor[0].curso_campus.diretoria.setor.uo
            professor = Professor.objects.filter(vinculo=servidor.get_vinculo()).first()
            if professor is None:
                self.erros.append(f'{servidor.get_vinculo().relacionamento.matricula}\tSEM PROFESSOR VINCULADO')
                continue
            servidor_estrangeiro = servidor.pessoa_fisica.nacionalidade == Nacionalidade.ESTRANGEIRO
            if not servidor_estrangeiro and (
                not professor.curso_superior_id or not professor.curso_superior.codigo or not professor.curso_superior.ativo
            ):
                self.erros.append(f'{professor.get_matricula()}\tSEM CODIGO CURSO SUPERIOR ATIVO')
                continue

            cod_indigena = ''
            if servidor.raca and servidor.raca.is_indigena():
                if not servidor.povo_indigena:
                    self.erros.append(f'{professor.get_matricula()}\tSEM POVO INDIGENA')
                    continue
                cod_indigena = servidor.povo_indigena.codigo_educacenso

            registro = []
            # 1	Tipo do registro
            registro.append(30)
            # 2 Código de escola - Inep
            registro.append(uo.codigo_inep)
            # 3	Código da pessoa física no sistema próprio
            registro.append(servidor.matricula)
            # 4	Identificação única (Inep)
            registro.append('')
            # 5 Número do CPF
            registro.append(formatar(servidor.pessoa_fisica.cpf))
            # 6 Nome completo
            registro.append(to_ascii(formatar(servidor.pessoa_fisica.nome_registro)))
            # 7 Data de Nascimento
            registro.append(servidor.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y'))
            # 8 Filiação
            nome_mae = formatar(servidor.pessoa_fisica.nome_mae or '')
            nome_pai = formatar(servidor.pessoa_fisica.nome_pai or '')
            registro.append((nome_mae or nome_pai) and 1 or 0)
            # 9 Filiação 1 (preferencialmente o nome da mãe)
            registro.append(nome_mae)
            # 10 Filiação 2 (preferencialmente o nome do pai)
            registro.append(nome_pai)
            # 11    Sexo        1    Fixo    Numérico    Obrigatório
            registro.append(servidor.pessoa_fisica.sexo == 'M' and 1 or 2)
            # 12    Cor/Raça        1    Fixo    Numérico    Obrigatório
            registro.append((servidor.raca.codigo_censup if servidor.raca else None) or 1)
            # 13 Povo indígena
            registro.append(cod_indigena)
            # 14    Nacionalidade        1    Fixo    Numérico    Obrigatório
            # 1 - Brasileiro
            # 2 - Brasileira - Nascido no exterior ou naturalizado
            # 3 - Estrangeiro

            if servidor.pessoa_fisica.nacionalidade == Nacionalidade.BRASILEIRO_NATO:
                registro.append(1)
            elif servidor.pessoa_fisica.nacionalidade in (Nacionalidade.BRASILEIRO_NATZ, Nacionalidade.EQUIPARADO):
                registro.append(2)
            else:
                registro.append(3)
            # 15 País de nacionalidade
            registro.append(nacionalidade)
            # 16    Município de Nascimento        7    Fixo    Númerico    Condicional
            registro.append(servidor.pessoa_fisica.nacionalidade == 1 and naturalidade and naturalidade.codigo or '')
            # 17 Pessoa física com deficiência, transtorno do espectro autista e altas habilidades ou superdotação
            registro.append(0)
            # 18 a 28 Deficiência, transtorno do espectro autista e altas habilidades ou superdotação
            # 18 Cegueira
            registro.append('')
            # 19 Baixa visão
            registro.append('')
            # 20 Visão monocular
            registro.append('')
            # 21 Surdez
            registro.append('')
            # 22 Deficiência auditiva
            registro.append('')
            # 23 Surdocegueira
            registro.append('')
            # 24 Deficiência física
            registro.append('')
            # 25 Deficiência intelectual
            registro.append('')
            # 26 Deficiência múltipla
            registro.append('')
            # 27 Transtorno do espectro autista
            registro.append('')
            # 28 Altas habilidades/ superdotação
            registro.append('')
            # 29 Pessoa física com transtorno(s) que impacta(m) o desenvolvimento da aprendizagem
            # 30 a 35 Transtorno(s) que impacta(m) o desenvolvimento da aprendizagem
            registro.append('')
            # 30 a 35 Tipo(s) de transtorno(s) que impacta(m) o desenvolvimento da aprendizagem
            # 30 Discalculia ou outro transtorno da matemática e raciocínio lógico
            registro.append('')
            # 31 Disgrafia, Disortografia ou outro transtorno da escrita e ortografia
            registro.append('')
            # 32 Dislalia ou outro transtorno da linguagem e comunicação
            registro.append('')
            # 33 Dislexia
            registro.append('')
            # 34 Transtorno do Déficit de Atenção com Hiperatividade (TDAH)
            registro.append('')
            # 35 Transtorno do Processamento Auditivo Central (TPAC)
            registro.append('')
            # 36 a 49 Recursos para uso do(a) aluno(a) em sala de aula e para participação em avaliações do Inep (Saeb)
            # 36 Auxílio ledor
            registro.append('')
            # 37 Auxílio transcrição
            registro.append('')
            # 38 Guia-Intérprete
            registro.append('')
            # 39 Tradutor-Intérprete de Libras
            registro.append('')
            # 40 Leitura Labial
            registro.append('')
            # 41 Prova Ampliada (Fonte 18)
            registro.append('')
            # 42 Prova superampliada (Fonte 24)
            registro.append('')
            # 43 CD com áudio para deficiente visual
            registro.append('')
            # 44 Prova de Língua Portuguesa como Segunda Língua para surdos e deficientes auditivos
            registro.append('')
            # 45 Prova em Vídeo em Libras
            registro.append('')
            # 46 Material didático em Braille
            registro.append('')
            # 47 Prova em Braille
            registro.append('')
            # 48 Tempo adicional
            registro.append('')
            # 49 Nenhum
            registro.append('')
            # 50 Número da matrícula da certidão de nascimento (certidão nova)
            registro.append('')
            # 51 País da residência
            registro.append('')
            # 52 CEP
            registro.append('')
            # 53 Município de residência
            registro.append('')
            # 54 Localização/ Zona de residência
            registro.append('')
            # 55 Localização diferenciada de residência
            # 7 - Não está em área de localização diferenciada
            # 1 - Área de assentamento
            # 2 - Terra indígena
            # 3 - Comunidade quilombola
            # 8 - Área onde se localizam povos e comunidades tradicionais
            registro.append('')
            # 56 Maior nível de escolaridade concluído
            # 1-Não concluiu o ensino fundamental
            # 2-Ensino fundamental
            # 7-Ensino médio
            # 6-Educação superior
            registro.append(6)
            # 57 Tipo de ensino médio cursado
            registro.append('')
            # 58 Código do Curso 1
            registro.append(professor.curso_superior.codigo)
            # 59 Ano de Conclusão 1
            registro.append(professor.ano_conclusao_curso_superior)
            # 60 Instituição de educação superior 1
            ies = (
                '9999999'
                if professor.instituicao_ensino_superior_id is None and servidor_estrangeiro
                else professor.instituicao_ensino_superior.codigo
            )
            registro.append(ies)
            # 61 Código do Curso 2
            registro.append('')
            # 62 Ano de Conclusão 2
            registro.append('')
            # 63 Instituição de educação superior 2
            registro.append('')
            # 64 Código do Curso 3
            registro.append('')
            # 65 Ano de Conclusão 3
            registro.append('')
            # 66 Instituição de educação superior 3
            registro.append('')

            # 67 a 69 Formação/Complementação pedagógica
            # 67 Área do conhecimento/ componentes curriculares 1
            registro.append('')
            # 68 Área do conhecimento/ componentes curriculares 2
            registro.append('')
            # 69 Área do conhecimento/ componentes curriculares 3
            registro.append('')

            # 70 a 88 Pós-Graduações concluídas
            titulacao = professor and professor.titulacao or ''
            titulacao_pos = 'speciali' in titulacao and 1 or 'estr' in titulacao and 2 or 'outor' in titulacao and 3 or ''
            # 70 Tipo de pós-graduação 1
            registro.append(titulacao_pos)
            # 71 Área da pós-graduação 1
            registro.append(titulacao_pos and int(professor.area_ultima_titulacao or 0) or '')
            # 72 Ano de conclusão da pós-graduação 1
            registro.append(titulacao_pos and professor.ano_ultima_titulacao and professor.ano_ultima_titulacao.ano or '')
            # 73 Tipo de pós-graduação 2
            registro.append('')
            # 74 Área da pós-graduação 2
            registro.append('')
            # 75 Ano de conclusão da pós-graduação 2
            registro.append('')
            # 76 Tipo de pós-graduação 3
            registro.append('')
            # 77 Área da pós-graduação 3
            registro.append('')
            # 78 Ano de conclusão da pós-graduação 3
            registro.append('')
            # 79 Tipo de pós-graduação 4
            registro.append('')
            # 80 Área da pós-graduação 4
            registro.append('')
            # 81 Ano de conclusão da pós-graduação 4
            registro.append('')
            # 82 Nível de pós-graduação 5
            registro.append('')
            # 83 Área da pós-graduação 5
            registro.append('')
            # 84 Ano de conclusão da pós-graduação 5
            registro.append('')
            # 85  Tipo de pós-graduação 6
            registro.append('')
            # 86 Área da pós-graduação 6
            registro.append('')
            # 87 Ano de conclusão da pós-graduação 6
            registro.append('')
            # 88 Não tem pós-graduação concluída
            registro.append((not titulacao or 'radua' in titulacao) and 1 or '')

            # 89 a 109 Outros cursos específicos (Formação continuada com mínimo de 80 horas)
            # 89 Creche (0 a 3 anos)
            registro.append(0)
            # 90 Pré-escola (4 e 5 anos)
            registro.append(0)
            # 91 Alfabetização [novo em 2026]
            registro.append(0)
            # 92 Anos iniciais do ensino fundamental
            registro.append(0)
            # 93 Anos finais do ensino fundamental
            registro.append(0)
            # 94 Ensino médio
            registro.append(0)
            # 95 Educação de jovens e adultos
            registro.append(0)
            # 96 Educação especial
            registro.append(0)
            # 97 Educação Indígena
            registro.append(0)
            # 98 Educação do campo
            registro.append(0)
            # 99 Educação ambiental
            registro.append(0)
            # 100 Educação em direitos humanos
            registro.append(0)
            # 101 Educação bilíngue de surdos
            registro.append(0)
            # 102 Educação e Tecnologia de Informação e Comunicação (TIC)
            registro.append(0)
            # 103 Educação integral em tempo integral [novo em 2026]
            registro.append(0)
            # 104 Gênero e diversidade sexual
            registro.append(0)
            # 105 Direitos de criança e adolescente
            registro.append(0)
            # 106 Educação para as relações étnico-raciais e História e cultura afro-brasileira e africana
            registro.append(0)
            # 107 Gestão Escolar
            registro.append(0)
            # 108 Outros
            registro.append(0)
            # 109 Nenhum
            registro.append(1)

            # 110 Endereço Eletrônico (e-mail)
            diretoria = Diretoria.objects.filter(setor__uo=uo, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).first()
            if diretoria is None:
                diretoria = Diretoria.objects.filter(setor__uo=uo, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).first()
                if diretoria is None:
                    self.erros.append(f'{uo}\tDIRETORIA NÃO LOCALIZADA')
                    continue
            registro.append(
                (servidor.get_vinculo().user == diretoria.diretor_geral.user or servidor.get_vinculo().user == diretoria.diretor_academico.user)
                and servidor.email_institucional
                and servidor.email_institucional.upper()
                or ''
            )
            self.adicionar(registro)

    def exportar_registros_30_alunos(self, alunos, task):
        for aluno in task.iterate(alunos):
            nome_pai = formatar(aluno.nome_pai or '')
            try:
                dados_rf = aluno.get_dados_receita_federal()
                nome_aluno = to_ascii(dados_rf.get('Nome').upper())
                nascimento_aluno = f'{dados_rf["DataNascimento"][6:8]}/{dados_rf["DataNascimento"][4:6]}/{dados_rf["DataNascimento"][0:4]}'
                nome_mae = formatar(dados_rf.get('NomeMae'))
                # Há casos em que o serviço, retorna o nome do pai como sendo o nome da mãe.
                # Nesses casos, utilizaremos a informação salva no SUAP
                if nome_mae == nome_pai:
                    nome_mae = formatar(aluno.nome_mae)
            except Exception:
                nome_aluno = to_ascii(formatar(aluno.pessoa_fisica.nome_registro))
                nascimento_aluno = aluno.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y')
                nome_mae = formatar(aluno.nome_mae)

            registro = []
            # 1	Tipo do registro
            registro.append(30)
            # 2 Código de escola - Inep
            registro.append(aluno.curso_campus.diretoria.setor.uo.codigo_inep)
            # 3	Código da pessoa física no sistema próprio
            registro.append(aluno.matricula)
            # 4	Identificação única (Inep)
            registro.append(aluno.codigo_educacenso or '')
            # 5 Número do CPF
            registro.append(formatar(aluno.pessoa_fisica.cpf))
            # 6 Nome completo
            registro.append(nome_aluno)
            # 7 Data de Nascimento
            registro.append(nascimento_aluno)
            # 8 Filiação
            registro.append((nome_mae or nome_pai) and 1 or 0)
            # 9 Filiação 1 (preferencialmente o nome da mãe)
            registro.append(nome_mae)
            # 10 Filiação 2 (preferencialmente o nome do pai)
            registro.append(nome_pai)
            # 11    Sexo        1    Fixo    Numérico    Obrigatório
            registro.append(aluno.pessoa_fisica.sexo == 'M' and 1 or 2)
            # 12    Cor/Raça        1    Fixo    Numérico    Obrigatório
            registro.append(aluno.raca.codigo_censup if aluno.raca else 1)
            # 13 Povo indígena
            registro.append(aluno.codigo_educacenso_indigena)
            # 14    Nacionalidade        1    Fixo    Numérico    Obrigatório
            # 1 - Brasileiro
            # 2 - Brasileira - Nascido no exterior ou naturalizado
            # 3 - Estrangeiro
            if aluno.nacionalidade == 'Brasileira':
                registro.append(1)
            elif aluno.nacionalidade == 'Brasileira - Nascido no exterior ou naturalizado':
                registro.append(2)
            else:
                registro.append(3)
            # 15 País de nacionalidade
            registro.append(aluno.codigo_educacenso_nacionalidade)
            # 16    Município de Nascimento        7    Fixo    Númerico    Condicional
            registro.append(aluno.nacionalidade == 'Brasileira' and aluno.naturalidade.codigo or '')
            # 17 Pessoa física com deficiência, transtorno do espectro autista e altas habilidades ou superdotação
            deficiencias = aluno.get_deficiencias_educacenso()
            possui_tea = Deficiencia.TEA in deficiencias
            deficiencias.discard(Deficiencia.TEA)
            altas_habilidades = aluno.get_nee_altashabilidades_educacenso()
            possui_nee = deficiencias or possui_tea or altas_habilidades
            registro.append(1 if possui_nee else 0)

            # 18 a 28 Tipo de deficiência, transtorno do espectro autista e altas habilidades ou superdotação
            if not possui_nee:
                for _ in range(11):
                    registro.append('')
            else:
                # 18 Cegueira
                registro.append(1 if Deficiencia.CEGUEIRA in deficiencias else 0)
                # 19 Baixa visão
                registro.append(1 if Deficiencia.BAIXA_VISAO in deficiencias else 0)
                # 20 Visão monocular
                registro.append(1 if Deficiencia.VISAO_MONOCULAR in deficiencias else 0)
                # 21 Surdez
                registro.append(1 if Deficiencia.SURDEZ in deficiencias else 0)
                # 22 Deficiência auditiva
                registro.append(1 if Deficiencia.DEFICIENCIA_AUDITIVA in deficiencias else 0)
                # 23 Surdocegueira
                registro.append(1 if Deficiencia.SURDOCEGUEIRA in deficiencias else 0)
                # 24 Deficiência física
                registro.append(1 if Deficiencia.DEFICIENCIA_FISICA in deficiencias else 0)
                # 25 Deficiência intelectual
                registro.append(1 if Deficiencia.DEFICIENCIA_INTELECTUAL in deficiencias else 0)
                # 26 Deficiência múltipla
                registro.append(1 if len(deficiencias) > 1 else 0)
                # 27 Transtorno do espectro autista
                registro.append(1 if possui_tea else 0)
                # 28 Altas habilidades/ superdotação
                registro.append(1 if TipoNEE.ALTAS_HABILIDADES in altas_habilidades else 0)

            # 29 a 35 Transtorno(s) que impacta(m) o desenvolvimento da aprendizagem
            # 29 Pessoa física com transtorno(s) que impacta(m) o desenvolvimento da aprendizagem
            outras_nees = aluno.get_outras_nees_educacenso()
            registro.append(1 if outras_nees else 0)
            if not outras_nees:
                for _ in range(6):
                    registro.append('')
            else:
                # 30 a 35 Tipo(s) de transtorno(s) que impacta(m) o desenvolvimento da aprendizagem
                # 30 Discalculia ou outro transtorno da matemática e raciocínio lógico
                registro.append(1 if TipoNEE.DISCALCULIA in outras_nees else 0)
                # 31 Disgrafia, Disortografia ou outro transtorno da escrita e ortografia
                registro.append(1 if TipoNEE.DISGRAFIA in outras_nees else 0)
                # 32 Dislalia ou outro transtorno da linguagem e comunicação
                registro.append(1 if TipoNEE.DISLALIA in outras_nees else 0)
                # 33 Dislexia
                registro.append(1 if TipoNEE.DISLEXIA in outras_nees else 0)
                # 34 Transtorno do Déficit de Atenção com Hiperatividade (TDAH)
                registro.append(1 if TipoNEE.TDAH in outras_nees else 0)
                # 35 Transtorno do Processamento Auditivo Central (TPAC)
                registro.append(1 if TipoNEE.TPAC in outras_nees else 0)

            # 36 a 49 Recursos para uso do(a) aluno(a) em sala de aula e para participação em avaliações do Inep (Saeb)
            possui_nee = possui_nee or outras_nees
            auxilio_ledor = 1 if Deficiencia.CEGUEIRA in deficiencias else 0
            auxilio_transcricao = 1 if Deficiencia.SURDOCEGUEIRA in deficiencias else 0
            guia_interprete = 1 if Deficiencia.SURDOCEGUEIRA in deficiencias else 0
            nenhum_auxilio = 0 if any(d in deficiencias for d in [Deficiencia.CEGUEIRA, Deficiencia.SURDOCEGUEIRA]) else 1
            # 36 Auxílio ledor
            registro.append(auxilio_ledor if possui_nee else '')
            # 37 Auxílio transcrição
            registro.append(auxilio_transcricao if possui_nee else '')
            # 38 Guia-Intérprete
            registro.append(guia_interprete if possui_nee else '')
            # 39 Tradutor-Intérprete de Libras
            registro.append(0 if possui_nee else '')
            # 40 Leitura Labial
            registro.append(0 if possui_nee else '')
            # 41 Prova Ampliada (Fonte 18)
            registro.append(0 if possui_nee else '')
            # 42 Prova superampliada (Fonte 24)
            registro.append(0 if possui_nee else '')
            # 43 CD com áudio para deficiente visual
            registro.append(0 if possui_nee else '')
            # 44 Prova de Língua Portuguesa como Segunda Língua para surdos e deficientes auditivos
            registro.append(0 if possui_nee else '')
            # 45 Prova em Vídeo em Libras
            registro.append(0 if possui_nee else '')
            # 46 Material didático em Braille
            registro.append(0 if possui_nee else '')
            # 47 Prova em Braille
            registro.append(0 if possui_nee else '')
            # 48 Tempo adicional
            registro.append(0 if possui_nee else '')
            # 49 Nenhum
            registro.append(nenhum_auxilio if possui_nee else '')

            # 50 Número da matrícula da certidão de nascimento (certidão nova)
            registro.append('')
            # 51 País da residência
            registro.append(76)
            # 52 CEP
            registro.append('')
            # 53 Município de residência
            registro.append('')
            # 54 Localização/ Zona de residência
            registro.append(aluno.tipo_zona_residencial)

            # 55 Localização diferenciada de residência
            # 7 - Não está em área de localização diferenciada
            # 1 - Área de assentamento
            # 2 - Terra indígena
            # 3 - Comunidade quilombola
            # 8 - Área onde se localizam povos e comunidades tradicionais
            registro.append('')
            # 56 Maior nível de escolaridade concluído
            registro.append('')
            # 57 Tipo de ensino médio cursado
            registro.append('')
            # 58 Código do Curso 1
            registro.append('')
            # 59 Ano de Conclusão 1
            registro.append('')
            # 60 Instituição de educação superior 1
            registro.append('')
            # 61 Código do Curso 2
            registro.append('')
            # 62 Ano de Conclusão 2
            registro.append('')
            # 63 Instituição de educação superior 2
            registro.append('')
            # 64 Código do Curso 3
            registro.append('')
            # 65 Ano de Conclusão 3
            registro.append('')
            # 66 Instituição de educação superior 3
            registro.append('')

            # 67 a 69 Formação/Complementação pedagógica
            # 67  Área do conhecimento/ componentes curriculares 1
            registro.append('')
            # 68  Área do conhecimento/ componentes curriculares 2
            registro.append('')
            # 69  Área do conhecimento/ componentes curriculares 3
            registro.append('')

            # 70 a 88 Pós-Graduações concluídas
            # 70 Tipo de pós-graduação 1
            registro.append('')
            # 71 Área da pós-graduação 1
            registro.append('')
            # 72 Ano de conclusão da pós-graduação 1
            registro.append('')
            # 73 Tipo de pós-graduação 2
            registro.append('')
            # 74 Área da pós-graduação 2
            registro.append('')
            # 75 Ano de conclusão da pós-graduação 2
            registro.append('')
            # 76 Tipo de pós-graduação 3
            registro.append('')
            # 77 Área da pós-graduação 3
            registro.append('')
            # 78 Ano de conclusão da pós-graduação 3
            registro.append('')
            # 79 Tipo de pós-graduação 4
            registro.append('')
            # 80 Área da pós-graduação 4
            registro.append('')
            # 81 Ano de conclusão da pós-graduação 4
            registro.append('')
            # 82 Nível de pós-graduação 5
            registro.append('')
            # 83 Área da pós-graduação 5
            registro.append('')
            # 84 Ano de conclusão da pós-graduação 5
            registro.append('')
            # 85 Tipo de pós-graduação 6
            registro.append('')
            # 86 Área da pós-graduação 6
            registro.append('')
            # 87 Ano de conclusão da pós-graduação 6
            registro.append('')
            # 88 Não tem pós-graduação concluída
            registro.append('')

            # 89 a 109 Outros cursos específicos (Formação continuada com mínimo de 80 horas)
            # 89 Creche (0 a 3 anos)
            registro.append('')
            # 90 Pré-escola (4 e 5 anos)
            registro.append('')
            # 91 Alfabetização [novo em 2026]
            registro.append('')
            # 92 Anos iniciais do ensino fundamental
            registro.append('')
            # 93 Anos finais do ensino fundamental
            registro.append('')
            # 94 Ensino médio
            registro.append('')
            # 95 Educação de jovens e adultos
            registro.append('')
            # 96 Educação especial
            registro.append('')
            # 97 Educação Indígena
            registro.append('')
            # 98 Educação do campo
            registro.append('')
            # 99 Educação ambiental
            registro.append('')
            # 100 Educação em direitos humanos
            registro.append('')
            # 101 Educação bilíngue de surdos
            registro.append('')
            # 102 Educação e Tecnologia de Informação e Comunicação (TIC)
            registro.append('')
            # 103 Educação integral em tempo integral [novo em 2026]
            registro.append('')
            # 104 Gênero e diversidade sexual
            registro.append('')
            # 105 Direitos de criança e adolescente
            registro.append('')
            # 106 Educação para as relações étnico-raciais e História e cultura afro-brasileira e africana
            registro.append('')
            # 107 Gestão Escolar
            registro.append('')
            # 108 Outros
            registro.append('')
            # 109 Nenhum
            registro.append('')
            # 110 Endereço Eletrônico (e-mail)
            registro.append('')
            self.adicionar(registro)

    def exportar_registros_40(self, turmas, uo, task):
        diretoria = Diretoria.objects.filter(setor__uo=uo, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).first()
        if diretoria is None:
            diretoria = Diretoria.objects.filter(setor__uo=uo, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).first()
            if diretoria is None:
                self.erros.append(f'{uo}\tDIRETORIA NÃO LOCALIZADA')
                return
        matriculas = [diretoria.diretor_geral.user.username, diretoria.diretor_academico.user.username]
        gestores = Servidor.objects.filter(matricula__in=matriculas)

        for servidor in gestores:
            turmas_professor = self.get_turmas_professor(servidor, turmas)
            if not turmas_professor:
                self.exportar_registros_30([servidor], None, uo, task)

        for servidor in gestores:
            registro = []
            # 1 Tipo de registro
            registro.append(40)
            # 2 Código de escola - Inep
            registro.append(uo.codigo_inep)
            # 3 Código da pessoa física no sistema próprio
            registro.append(servidor.matricula)
            # 4 Identificação única (Inep)
            registro.append('')
            # 5 Cargo
            #     1: Diretor(a)
            #     2: Outro Cargo
            registro.append(2)
            # 6 Critério de acesso ao cargo/função
            registro.append('')
            # 7 Situação Funcional/ Regime de contratação/Tipo de vínculo
            registro.append(1)
            self.adicionar(registro)

    def exportar_registros_50(self, professores, turmas, task):
        for servidor in task.iterate(professores):
            if self.check_servidor(servidor)[0]:
                continue
            professor = Professor.objects.get(vinculo=servidor.get_vinculo())
            turmas_unicas = set()
            for turma in turmas.filter(diario__professordiario__professor=professor):
                if turma in turmas_unicas:
                    continue
                diarios_professor = self.get_diarios_turma(turma, professor)
                if diarios_professor.exists():
                    turmas_unicas.add(turma)
                    registro = []
                    # 1 Tipo de registro
                    registro.append(50)
                    # 2 Código de escola - Inep
                    registro.append(turma.curso_campus.diretoria.setor.uo.codigo_inep)
                    # 3 Código da pessoa física no sistema próprio
                    registro.append(servidor.matricula)
                    # 4 Identificação única (Inep)
                    registro.append('')
                    # 5 Código da Turma na Entidade/Escola
                    codigo_turma = turma.codigo.replace('.', '')
                    registro.append(codigo_turma)
                    # 6 Código da turma no INEP
                    registro.append('')
                    # 7 Função que exerce na escola/Turma
                    is_presencial = not turma.curso_campus.diretoria.ead
                    registro.append(is_presencial and 1 or 5)
                    # 8 Situação Funcional/ Regime de contratação/Tipo de Vínculo
                    registro.append(servidor.situacao.nome in ('CONT.PROF.SUBSTITUTO', 'CONT.PROF.TEMPORARIO') and 2 or 1)
                    # 9 a 33 Áreas do conhecimento/componentes curriculares que leciona
                    disciplinas = []
                    etapa_agregada, etapa = self.get_etapa(turma)
                    if not etapa:
                        disciplinas.append('17')
                    else:
                        if self.possui_disciplina_quimica(diarios_professor, etapa):
                            disciplinas.append('1')

                        if self.possui_disciplina_fisica(diarios_professor, etapa):
                            disciplinas.append('2')

                        if self.possui_disciplina_matematica(diarios_professor, etapa):
                            disciplinas.append('3')

                        if self.possui_disciplina_biologia(diarios_professor, etapa):
                            disciplinas.append('4')

                        if self.possui_disciplina_portugues(diarios_professor, etapa):
                            disciplinas.append('6')

                        if self.possui_disciplina_ingles(diarios_professor, etapa):
                            disciplinas.append('7')

                        if self.possui_disciplina_espanhol(diarios_professor, etapa):
                            disciplinas.append('8')

                        if self.possui_disciplina_artes(diarios_professor, etapa):
                            disciplinas.append('10')

                        if self.possui_disciplina_educacao_fisica(diarios_professor, etapa):
                            disciplinas.append('11')

                        if self.possui_disciplina_historia(diarios_professor, etapa):
                            disciplinas.append('12')

                        if self.possui_disciplina_geografia(diarios_professor, etapa):
                            disciplinas.append('13')

                        if self.possui_disciplina_filosofia(diarios_professor, etapa):
                            disciplinas.append('14')

                        if self.possui_disciplina_informatica(diarios_professor, etapa):
                            disciplinas.append('16')

                        if self.possui_disciplina_profissionalizante(diarios_professor, etapa):
                            disciplinas.append('17')

                        if self.possui_disciplina_libras(diarios_professor, etapa):
                            disciplinas.append('23')

                        if self.possui_disciplina_sociologia(diarios_professor, etapa):
                            disciplinas.append('29')

                        if self.possui_disciplina_frances(diarios_professor, etapa):
                            disciplinas.append('30')

                        if self.possui_outras_disciplinas(diarios_professor, etapa):
                            disciplinas.append('99')

                    disciplinas = list(set(disciplinas))
                    for _i in range(len(disciplinas), 25):
                        disciplinas.append('')
                    # 9 a 33 Áreas do conhecimento/componentes curriculares - Código 1 a 25
                    registro.extend(disciplinas)
                    # 34 a 37 Área(s) do itinerário formativo
                    # 34 Linguagens e suas tecnologias
                    registro.append('')
                    # 35 Matemática e suas tecnologias
                    registro.append('')
                    # 36 Ciências da natureza e suas tecnologias
                    registro.append('')
                    # 37 Ciências humanas e sociais aplicadas
                    registro.append('')
                    # 38 Profissional escolar leciona no Itinerário de formação técnica e profissional (IFTP)
                    registro.append('1' if etapa_agregada in [304, 305] else '')
                    self.adicionar(registro)

    def exportar_registros_60(self, alunos, task):
        for aluno in task.iterate(alunos):
            turma = aluno.turma
            is_presencial = not turma.curso_campus.diretoria.ead
            registro = []
            # 1	Tipo de registro
            registro.append(60)
            # 2 Código de escola - Inep
            registro.append(aluno.curso_campus.diretoria.setor.uo.codigo_inep)
            # 3 Código da pessoa física no sistema próprio
            registro.append(aluno.matricula)
            # 4	Identificação única (Inep)
            registro.append(aluno.codigo_educacenso or '')
            # 5 Código da Turma na Entidade/Escola
            codigo_turma = turma.codigo.replace('.', '')
            registro.append(codigo_turma)
            # 6 Código da turma no INEP
            registro.append('')
            # 7 Código da Matrícula do Aluno
            registro.append('')
            # 8 Turma multi
            registro.append('')
            # Carga horária integralizada pelo(a) aluno(a) no curso técnico ou de qualificação profissional (em horas) [novo em 2026]
            etapa_agregada, etapa = self.get_etapa(turma)
            if etapa_agregada in [304, 305] or etapa in [39, 40, 67, 68, 73, 75]:
                registro.append(aluno.get_carga_horaria_total_cumprida())
            else:
                registro.append('')
            # 10 a 20 Tipo de atendimento educacional especializado
            # 10 Desenvolvimento de funções cognitivas
            registro.append('')
            # 11 Desenvolvimento de vida autônoma
            registro.append('')
            # 12 Enriquecimento curricular
            registro.append('')
            # 13 Ensino da informática acessível
            registro.append('')
            # 14 Ensino da Língua Brasileira de Sinais (Libras)
            registro.append('')
            # 15 Ensino da Língua Portuguesa como Segunda Língua
            registro.append('')
            # 16 Ensino das técnicas do cálculo no Soroban
            registro.append('')
            # 17 Ensino de Sistema Braille
            registro.append('')
            # 18 Ensino de técnicas para orientação e mobilidade
            registro.append('')
            # 19 Ensino de uso da Comunicação Alternativa e Aumentativa (CAA)
            registro.append('')
            # 20 Ensino de uso de recursos ópticos e não ópticos
            registro.append('')
            # 21 Recebe escolarização em outro espaço (diferente da escola)
            registro.append(is_presencial and 1 or '')
            # 22 Transporte escolar público
            usa_transporte_publico = is_presencial and (aluno.poder_publico_responsavel_transporte and '1' or '0') or ''
            registro.append(usa_transporte_publico)
            # 23 Poder Público responsável pelo transporte escolar
            if usa_transporte_publico == '1':
                if aluno.poder_publico_responsavel_transporte == '1':
                    registro.append('2')
                else:
                    registro.append('1')
            else:
                registro.append('')
            # 24 a 33 Tipo de veículo utilizado no transporte escolar público
            valor_vazio = is_presencial and aluno.poder_publico_responsavel_transporte and '0' or ''
            # 24 Rodoviário - Bicicleta
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.BICICLETA and '1' or valor_vazio)
            # 25 - Microônibus
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.KOMBI_MICRO_ONIBUS and '1' or valor_vazio)
            # 26 Rodoviário - Ônibus
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.ONIBUS and '1' or valor_vazio)
            # 27 Rodoviário - Tração Animal
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.TRACAO_ANIMAL and '1' or valor_vazio)
            # 28 Rodoviário - Vans/Kombis
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.VANS_WV and '1' or valor_vazio)
            # 29 Rodoviário - Outro
            registro.append(is_presencial and aluno.tipo_veiculo in [Aluno.OUTRO_VEICULO_RODOVIARIO, Aluno.TREM] and '1' or valor_vazio)
            # 30 Aquaviário - Capacidade de até 5 aluno(a)s
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.AQUAVIARIO_ATE_5 and '1' or valor_vazio)
            # 31 Aquaviário - Capacidade entre 5 a 15 aluno(a)s
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.AQUAVIARIO_ENTRE_5_A_15 and '1' or valor_vazio)
            # 32 - Aquaviário - Capacidade entre 15 a 35 aluno(a)s
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.AQUALVIARIO_ENTRE_15_E_35 and '1' or valor_vazio)
            # 33 - Aquaviário - Capacidade acima de 35 aluno(a)s
            registro.append(is_presencial and aluno.tipo_veiculo == Aluno.AQUAVIARIO_ACIMA_DE_35 and '1' or valor_vazio)
            self.adicionar(registro)

    def get_turma(self, matricula_periodo):
        turma = matricula_periodo.turma if matricula_periodo.turma_id else None
        if turma is None and self.inferir_turma:
            md = (
                matricula_periodo.matriculadiario_set.filter(diario__turma__matriz_id=matricula_periodo.aluno.matriz_id)
                .select_related('diario__turma')
                .order_by('-diario__turma__periodo_matriz')
                .first()
            )
            if md:
                turma = md.diario.turma
        return turma

    def get_diarios_turma(self, turma, professor=None):
        qs = turma.diario_set.exclude(professordiario__isnull=True).exclude(
            componente_curricular__nucleo__descricao='Fundamental',
            turma__curso_campus__modalidade_id__in=[
                Modalidade.SUBSEQUENTE,
                Modalidade.CONCOMITANTE,
                Modalidade.PROEJA_FIC_FUNDAMENTAL,
                Modalidade.FIC,
            ],
        )

        if professor:
            qs = qs.filter(professordiario__professor=professor)
        return qs

    def get_etapa(self, turma):
        etapa = ''
        etapa_agregada = ''
        if turma.curso_campus.modalidade_id in (Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA):
            etapa = 74
            etapa_agregada = 306
        elif turma.curso_campus.modalidade_id in [Modalidade.PROEJA_FIC_FUNDAMENTAL, Modalidade.FIC]:
            etapa = 68  # 73
            etapa_agregada = 308  # 306
        elif turma.curso_campus.modalidade_id == Modalidade.SUBSEQUENTE:
            etapa = 40
            etapa_agregada = 308
        elif turma.curso_campus.modalidade_id == Modalidade.CONCOMITANTE:
            etapa = 39
            etapa_agregada = 308
        elif turma.curso_campus.modalidade_id == Modalidade.INTEGRADO:
            etapa = (
                turma.periodo_matriz == 1
                and 25
                or turma.periodo_matriz == 2
                and 26
                or turma.periodo_matriz == 3
                and 27
                or turma.periodo_matriz == 4
                and 28
                or ''
            )
            etapa_agregada = 304

        return etapa_agregada, etapa

    def check_aluno(self, aluno):
        apto = True
        matricula_periodo = aluno.matriculaperiodo_set.filter(ano_letivo__ano=self.ano, periodo_letivo=1)[0]

        turma = self.get_turma(matricula_periodo)
        if not turma:
            ultimo_prodecimento = matricula_periodo.procedimentomatricula_set.order_by('-data').first()
            ultimo_tipo = ultimo_prodecimento and ultimo_prodecimento.tipo or ''
            ultimo_data = ultimo_prodecimento and ultimo_prodecimento.data.strftime('%d/%m/%Y') or ''
            self.erros.append(
                f'{aluno.matricula}\t{aluno.get_cpf()}\tSEM TURMA\t{aluno.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus.diretoria}\t{aluno.situacao}\t{ultimo_tipo}\t{ultimo_data}\t{aluno.curso_campus}'
            )
            apto = False
        if apto and not self.get_diarios_turma(turma).exists():
            self.erros.append(
                f'{aluno.matricula}\t{aluno.get_cpf()}\tCODIGO TURMA\t{aluno.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus.diretoria}\t{aluno.situacao}\t{aluno.curso_campus}'
            )
            apto = False

        if apto:
            qs = matricula_periodo.matriculadiario_set.exclude(diario__professordiario__isnull=True).exclude(
                diario__componente_curricular__nucleo__descricao='Fundamental',
                diario__turma__curso_campus__modalidade_id__in=[
                    Modalidade.SUBSEQUENTE,
                    Modalidade.CONCOMITANTE,
                    Modalidade.PROEJA_FIC_FUNDAMENTAL,
                    Modalidade.FIC,
                ],
            )
            if not qs.exists():
                apto = False

        nacionalidade = (
            76 if aluno.nacionalidade == 'Brasileira - Nascido no exterior ou naturalizado' or aluno.nacionalidade == 'Brasileira' else None
        )
        if apto and nacionalidade is None:
            from comum.models import Pais

            pais = Pais.objects.filter(nome__unaccent__iexact=aluno.pais_origem.nome).first() if aluno.pais_origem_id else None
            if pais and pais.codigo_educacenso:
                nacionalidade = pais.codigo_educacenso
            else:
                self.erros.append(
                    f'{aluno.matricula}\t{aluno.get_cpf()}\tSEM CODIGO PAIS\t{aluno.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus.diretoria}\t{aluno.situacao}\t{aluno.curso_campus}'
                )
                apto = False
        if apto and aluno.nacionalidade == 'Brasileira' and not aluno.naturalidade_id:
            self.erros.append(
                f'{aluno.matricula}\t{aluno.get_cpf()}\tSEM NATURALIDADE\t{turma.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus}'
            )
            apto = False

        codigo_educacenso_indigena = ''
        if apto and aluno.raca and aluno.raca.is_indigena():
            if not aluno.povo_indigena:
                self.erros.append(
                    f'{aluno.matricula}\t{aluno.get_cpf()}\tSEM POVO INDIGENA\t{turma.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus}'
                )
                apto = False
            else:
                codigo_educacenso_indigena = aluno.povo_indigena.codigo_educacenso

        return apto, turma, nacionalidade, codigo_educacenso_indigena

    def check_servidor(self, servidor):
        tem_erro = False

        # naturalidade
        qs_naturalidade = Cidade.objects.none()
        if servidor.nacionalidade == 1:
            if not servidor.nascimento_municipio_id:
                self.erros.append(f'{servidor.matricula}\tBRASILEIRO SEM NATURALIDADE')
                tem_erro = True
            elif not servidor.nascimento_municipio.uf:
                self.erros.append(f'{servidor.matricula}\tBRASILEIRO SEM UF')
                tem_erro = True
            else:
                nome_municipio = servidor.nascimento_municipio.nome.upper()
                qs_naturalidade = Cidade.objects.filter(
                    nome__in=(to_ascii(nome_municipio), nome_municipio), estado_id=Estado.ESTADOS[servidor.nascimento_municipio.uf]
                )
                qs_naturalidade = qs_naturalidade | Cidade.objects.filter(nome__iexact=servidor.nascimento_municipio.nome, codigo__isnull=False)
                if not qs_naturalidade.exists():
                    tem_erro = True
                    self.erros.append(
                        f'{servidor.matricula}\tCODIGO DA NATURALIDADE ERRADO ({to_ascii(servidor.nascimento_municipio.nome).upper()}, {servidor.nascimento_municipio.nome.upper()})'
                    )
            if tem_erro:
                try:
                    dados_rf = servidor.get_dados_receita_federal()
                    nomeMunicipioNaturalidade = dados_rf['NomeMunicipioNaturalidade']
                    ufMunicipioNaturalidade = dados_rf['UFMunicipioNaturalidade']
                    if nomeMunicipioNaturalidade and ufMunicipioNaturalidade:
                        estado = Estado.get_estado_por_sigla(ufMunicipioNaturalidade)
                        if estado:
                            qs_naturalidade = Cidade.objects.filter(nome__unaccent__iexact=nomeMunicipioNaturalidade, estado_id=estado.id)
                            if qs_naturalidade.exists():
                                tem_erro = False
                except Exception:
                    pass
        naturalidade = qs_naturalidade.first() if not tem_erro else None

        # nacionalidade
        nacionalidade = None
        if servidor.nacionalidade in (1, 2, 3):
            nacionalidade = 76
        elif servidor.pais_origem and servidor.pais_origem.codigo_educacenso:
            nacionalidade = servidor.pais_origem.codigo_educacenso
        else:
            self.erros.append(f'{servidor.matricula}\tSEM CODIGO PAIS')
            tem_erro = True

        return tem_erro, naturalidade, nacionalidade

    def get_turmas_professor(self, servidor, turmas):
        lista = []
        professor = Professor.objects.filter(vinculo=servidor.get_vinculo()).first()
        if professor:
            for turma in turmas.filter(diario__professordiario__professor=professor):
                if turma.diario_set.exclude(
                    componente_curricular__nucleo__descricao='Fundamental',
                    turma__curso_campus__modalidade_id__in=[
                        Modalidade.SUBSEQUENTE,
                        Modalidade.CONCOMITANTE,
                        Modalidade.PROEJA_FIC_FUNDAMENTAL,
                        Modalidade.FIC,
                    ],
                ).exists():
                    if turma.get_alunos_matriculados().exists() or (self.inferir_turma and turma.get_alunos_matriculados_diarios().exists()):
                        if turma not in lista:
                            lista.append(turma)
        return lista

    def possui_disciplina_quimica(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(
            componente_curricular__componente__descricao__unaccent__icontains='Química', componente_curricular__nucleo__descricao='Estruturante'
        ).exists()

    def possui_disciplina_fisica(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return (
            qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Física')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Educação física')
            .exists()
        )

    def possui_disciplina_matematica(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Matemática').exists()

    def possui_disciplina_biologia(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Biologi').exists()

    def possui_disciplina_portugues(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Portugu').exists()

    def possui_disciplina_ingles(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Ingl').exists()

    def possui_disciplina_espanhol(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Espanhol').exists()

    def possui_disciplina_artes(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Arte I').exists()

    def possui_disciplina_educacao_fisica(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Educação física').exists()

    def possui_disciplina_historia(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='História').exists()

    def possui_disciplina_geografia(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Geografia').exists()

    def possui_disciplina_filosofia(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return (
            qs.filter(componente_curricular__nucleo__descricao='Estruturante')
            .filter(componente_curricular__componente__descricao__unaccent__icontains='Filosofia')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Filosofia,')
            .exists()
        )

    def possui_disciplina_informatica(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return (
            qs.exclude(componente_curricular__nucleo__descricao='Tecnológico')
            .filter(componente_curricular__componente__descricao__unaccent__icontains='Informática')
            .exists()
        )

    def possui_disciplina_profissionalizante(self, qs, etapa):
        etapas = Exportador.ETAPAS_EJA + Exportador.ETAPAS_TECNICO
        if etapa not in etapas:
            return False
        nucleos = ['Tecnológico', 'Articulador', 'Específico']
        if etapa in Exportador.ETAPAS_EJA:
            nucleos.append('Fundamental')
        return (
            qs.filter(componente_curricular__nucleo__descricao__in=nucleos).exists() or qs.filter(turma__curso_campus__programa='PartiuIF').exists()
        )

    def possui_disciplina_libras(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Libras').exists()

    def possui_disciplina_sociologia(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return (
            qs.filter(componente_curricular__nucleo__descricao='Estruturante')
            .filter(componente_curricular__componente__descricao__unaccent__icontains='Sociologia')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Sociologia d')
            .exists()
        )

    def possui_disciplina_frances(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        return qs.filter(componente_curricular__componente__descricao__unaccent__icontains='Franc').exists()

    def possui_outras_disciplinas(self, qs, etapa):
        etapas = Exportador.ETAPAS_MEDIO + Exportador.ETAPAS_EJA
        if etapa not in etapas:
            return False
        if self.possui_componente_tecnologico_seminario(qs):
            return True
        return (
            qs.exclude(
                componente_curricular__componente__descricao__unaccent__icontains='Química', componente_curricular__nucleo__descricao='Estruturante'
            )
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Física')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Matemática')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Biologi')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Portugu')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Ingl')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Espanhol')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Arte I')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Educação física')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='História')
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Geografia')
            .exclude(
                componente_curricular__componente__descricao__unaccent__icontains='Filosofia', componente_curricular__nucleo__descricao='Estruturante'
            )
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Informática')
            .exclude(componente_curricular__nucleo__descricao='Tecnológico')
            .exclude(
                componente_curricular__componente__descricao__unaccent__icontains='Sociologia',
                componente_curricular__nucleo__descricao='Estruturante',
            )
            .exclude(componente_curricular__componente__descricao__unaccent__icontains='Franc')
            .exists()
        )

    def possui_componente_tecnologico_seminario(self, qs):
        return qs.filter(
            componente_curricular__nucleo__descricao='Tecnológico',
            componente_curricular__tipo=ComponenteCurricular.TIPO_SEMINARIO,
        ).exists()


class ExportadorEtapa2:
    def __init__(self, ano, uo, ignorar_erros, task):
        self.ano = ano
        self.uo = uo
        self.ignorar_erros = ignorar_erros
        self.registros = []
        self.erros = []

        self.modalidades = MODALIDADES

        # data corte é última quarta feira de maio
        primeiro_dia_junho = datetime.datetime(self.ano, 6, 1)
        data_corte = primeiro_dia_junho - datetime.timedelta(days=1)
        while data_corte.weekday() != 2:
            data_corte -= datetime.timedelta(days=1)

        dados = []
        uos = self.uo and [self.uo] or UnidadeOrganizacional.objects.suap().all()

        for uo in uos:
            alunos = Aluno.objects.filter(
                curso_campus__modalidade__in=self.modalidades,
                matriculaperiodo__ano_letivo__ano=self.ano,
                matriculaperiodo__periodo_letivo=1,
                curso_campus__diretoria__setor__uo=uo,
            )

            # retira matriculados após data de corte
            alunos = alunos.exclude(data_matricula__gt=data_corte.date())

            # retira transferidos internos
            alunos = alunos.exclude(situacao=SituacaoMatricula.TRANSFERIDO_INTERNO)

            # retira alunos formados antes da data de corte
            alunos = alunos.exclude(
                situacao_id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO], dt_conclusao_curso__lt=data_corte.date()
            )

            # retira alunos inativos antes da data de corte
            ids_alunos_remover = []
            for aluno in alunos.filter(
                situacao_id__in=[
                    SituacaoMatricula.JUBILADO,
                    SituacaoMatricula.EVASAO,
                    SituacaoMatricula.CANCELADO,
                    SituacaoMatricula.TRANSFERIDO_EXTERNO,
                    SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                    SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
                    SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
                    SituacaoMatricula.TRANCADO,
                    SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
                    SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                    SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO,
                ]
            ).only('id'):
                data = aluno.get_data_ultimo_procedimento_periodo_referencia()
                if data and data < data_corte.date():
                    ids_alunos_remover.append(aluno.id)
            alunos = alunos.exclude(id__in=ids_alunos_remover)

            alunos = alunos.order_by('pessoa_fisica__cpf').order_by('-matriculaperiodo').distinct()

            dados.append((uo, alunos))

        for _uo, alunos in dados:
            task.count(alunos)

        for uo, alunos in dados:
            self.exportar_registros_89(uo)
            self.exportar_registros_90_91(alunos, task)
            file_path = os.path.join(settings.TEMP_DIR, 'educacenso.txt')
            if self.ignorar_erros:
                s = '\r\n'.join(self.registros)
            else:
                s = '\r\n'.join(self.erros)
            with open(file_path, 'w') as f:
                f.write(s)
            task.finalize('Arquivo gerado com sucesso', '/edu/relatorio_educacenso_etapa_2/', file_path=file_path)

    def adicionar(self, registro):
        for i, item in enumerate(registro):
            registro[i] = str(item)
        self.registros.append('|'.join(registro))

    def exportar_registros_89(self, uo):
        siglas = uo.sigla == 'EAD' and (uo.sigla, 'CNAT') or (uo.sigla,)
        diretoria = Diretoria.objects.filter(setor__uo__sigla__in=siglas).first()

        if diretoria is None:
            self.erros.append(f'{siglas}\tSEM DIRETORIA')
            return

        if diretoria.diretor_geral_id is None:
            self.erros.append(f'{diretoria.setor}\tSEM DIRETOR GERAL')
            return

        qs_calendario_academico = CalendarioAcademico.objects.exclude(descricao__unaccent__icontains='depend').filter(
            diario__turma__curso_campus__diretoria__setor__uo=uo,
            diario__turma__curso_campus__modalidade=Modalidade.INTEGRADO,
            diario__ano_letivo__ano=self.ano,
            diario__componente_curricular__qtd_avaliacoes=4,
        )

        if not (uo.sigla in ['ZL', 'JUC'] or qs_calendario_academico.exists()):
            self.erros.append(f'{diretoria.setor}\tSEM CALENDÁRIO ANUAL PARA CURSO INTEGRADO')
            return

        servidor = diretoria.diretor_geral.relacionamento
        registro = []
        # 1 Tipo de registro
        registro.append(89)
        # 2 Código de escola - Inep
        registro.append(uo.codigo_inep)
        # 3 Número do CPF do Gestor Escolar
        registro.append(formatar(servidor.pessoa_fisica.cpf))
        # 4 Nome do Gestor Escolar
        registro.append(formatar(servidor.pessoa_fisica.nome_registro))
        self.adicionar(registro)

    def exportar_registros_90_91(self, alunos, task):
        l90 = []
        l91 = []
        for aluno in task.iterate(alunos):
            matricula_periodo = aluno.matriculaperiodo_set.filter(ano_letivo__ano=self.ano, periodo_letivo=1).order_by('-periodo_letivo')[0]
            turma = self.get_turma(matricula_periodo)
            if not turma:
                self.erros.append(
                    f'{aluno.matricula}\t{aluno.get_cpf()}\tSEM TURMA\t{aluno.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus.diretoria}\t{aluno.situacao}'
                )
                continue

            if not turma.codigo_educacenso:
                self.erros.append(
                    f'{turma.codigo}\tCODIGO EDUCACENSO\t{turma.curso_campus.diretoria.setor.uo.sigla}\t{turma.curso_campus.diretoria}\t{aluno.situacao}'
                )
                continue

            if not aluno.codigo_educacenso:
                self.erros.append(
                    f'{aluno.matricula}\t{aluno.get_cpf()}\tCODIGO EDUCACENSO\t{aluno.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus.diretoria}\t{aluno.situacao}'
                )
                continue

            if not matricula_periodo.codigo_educacenso:
                self.erros.append(
                    f'{aluno.matricula} {matricula_periodo.ano_letivo}/{matricula_periodo.periodo_letivo}\t{aluno.get_cpf()}\tCODIGO MATRICULA EDUCACENSO\t{aluno.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus.diretoria}\t{aluno.situacao}'
                )
                continue

            if matricula_periodo.situacao_id == SituacaoMatriculaPeriodo.TRANSF_CURSO:
                self.erros.append(
                    f'{aluno.matricula}\t{aluno.get_cpf()}\tTRANSFERIDO DE CURSO\t{aluno.curso_campus.diretoria.setor.uo.sigla}\t{aluno.curso_campus.diretoria}\t{aluno.situacao}'
                )

            if (
                not matricula_periodo.matriculadiario_set.exclude(
                    diario__componente_curricular__tipo=ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                    diario__componente_curricular__pode_fechar_pendencia=True,
                )
                .exclude(diario__professordiario__isnull=True)
                .exclude(diario__professordiario__professor__vinculo__pessoa__pessoafisica__nascimento_municipio__isnull=True)
                .exists()
            ):
                continue

            situacao = None
            if aluno.situacao_id in [
                SituacaoMatricula.TRANSFERIDO_INTERNO,
                SituacaoMatricula.TRANSFERIDO_EXTERNO,
                SituacaoMatricula.TRANSFERIDO_SUAP,
            ]:
                situacao = 1
            elif aluno.situacao_id in [
                SituacaoMatricula.EVASAO,
                SituacaoMatricula.JUBILADO,
                SituacaoMatricula.CANCELADO,
                SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
                SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            ]:
                situacao = 2
            elif aluno.situacao_id == SituacaoMatricula.FALECIDO:
                situacao = 3
            elif aluno.situacao_id == SituacaoMatricula.CONCLUIDO:
                situacao = 6
            if aluno.curso_campus.modalidade_id == Modalidade.INTEGRADO:
                if matricula_periodo.situacao_id in [SituacaoMatriculaPeriodo.REPROVADO, SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA]:
                    situacao = 4

                elif matricula_periodo.situacao_id == SituacaoMatriculaPeriodo.APROVADO and aluno.situacao_id == SituacaoMatricula.CONCLUIDO:
                    situacao = 6

                elif matricula_periodo.situacao_id in [
                    SituacaoMatriculaPeriodo.APROVADO,
                    SituacaoMatriculaPeriodo.MATRICULADO,
                    SituacaoMatriculaPeriodo.DEPENDENCIA,
                    SituacaoMatriculaPeriodo.TRANCADA,
                    SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
                    SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                ]:
                    situacao = 5

                elif situacao is None and matricula_periodo.situacao_id in [
                    SituacaoMatriculaPeriodo.CANCELADA,
                    SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
                    SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
                    SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
                    SituacaoMatriculaPeriodo.EVASAO,
                    SituacaoMatriculaPeriodo.JUBILADO,
                ]:
                    situacao = 2

                elif situacao is None and matricula_periodo.situacao_id in (
                    SituacaoMatriculaPeriodo.TRANSF_EXTERNA,
                    SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO,
                ):
                    situacao = 1

            if situacao is None and aluno.curso_campus.modalidade_id != Modalidade.INTEGRADO:
                situacao = 8

            registro = []
            # 1    Tipo de registro
            registro.append(90)
            # 2 Código da escola  INEP
            registro.append(aluno.curso_campus.diretoria.setor.uo.codigo_inep)
            # 3 Código da turma na entidade/escola
            registro.append('')
            # 4 Código da turma  INEP
            registro.append(turma.codigo_educacenso)
            # 5 Código de identificação única do aluno  INEP
            registro.append(aluno.codigo_educacenso)
            # 6 Código de identificação única do aluno na entidade/escola
            registro.append('')
            # 7 Código da matrícula
            registro.append(matricula_periodo.codigo_educacenso)
            # 8 Situação do aluno
            registro.append(situacao)
            l90.append(registro)

            registro = []
            # 1    Tipo de registro
            registro.append(91)
            # 2 Código da escola  INEP
            registro.append(aluno.curso_campus.diretoria.setor.uo.codigo_inep)
            # 3 Código da turma na entidade/escola
            registro.append('')
            # 4 Código da turma  INEP
            registro.append(turma.codigo_educacenso)
            # 5 Código de identificação única do aluno  INEP
            registro.append(aluno.codigo_educacenso)
            # 6 Código de identificação única do aluno na entidade/escola
            registro.append('')
            # 7 Código da matrícula
            registro.append('')
            # 8 Tipo de mediação didático pedagógico
            registro.append('')
            # 9 Código da etapa
            registro.append('')
            # 10 Situação do aluno
            registro.append(situacao)
            l91.append(registro)

        for registro in l90:
            self.adicionar(registro)
        for _registro in l91:
            pass
            # self.adicionar(registro) uso adiado

    def get_turma(self, matricula_periodo):
        turma = matricula_periodo.turma_id and matricula_periodo.turma or None
        if turma is None:
            md = matricula_periodo.matriculadiario_set.filter(
                diario__componente_curricular__tipo=ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL
            ).first()
            turma = md and md.diario.turma or None
        return turma
