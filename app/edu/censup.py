import os
import re
import tempfile

from django.conf import settings
from django.db.models import Q

from comum.models import Configuracao
from djtools.utils import mask_cpf, to_ascii
from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import Deficiencia, FormaIngresso, Modalidade, NivelEnsino, SituacaoMatricula, SituacaoMatriculaPeriodo
from edu.models.diarios import Diario, ProfessorDiario
from edu.models.professores import Professor
from rh.models import Servidor, ServidorFuncaoHistorico, ServidorAfastamento


class Exportador:
    DOCENTE = 1
    ALUNOS = 2
    LABORATORIO = 3

    def __init__(self, tipo, ano, uos=None, amostra=True, cpfs=None, ignorar_cpfs=None, ignorar_data_conclusao=False, task=None):
        if ignorar_cpfs is None:
            ignorar_cpfs = []
        if cpfs is None:
            cpfs = []
        self.tipo = tipo
        self.ano = ano
        self.uos = uos
        self.registros = []
        self.amostra = amostra
        self.cpfs = []
        self.ignorar_cpfs = []
        self.ignorar_data_conclusao = ignorar_data_conclusao
        self.task = task
        self.cpf_operador = self.task.user and self.task.user.get_profile().cpf or None
        self.codigo_mec = Configuracao.get_valor_por_chave('edu', 'codigo_mec') or 1082

        for cpf in cpfs:
            self.cpfs.append(mask_cpf(cpf, clean=False))
        for cpf in ignorar_cpfs:
            self.ignorar_cpfs.append(mask_cpf(cpf, clean=False))

        if tipo == Exportador.DOCENTE:
            self.exportar_docentes()
        elif tipo == Exportador.ALUNOS:
            self.exportar_alunos()
        elif tipo == Exportador.LABORATORIO:
            self.exportar_laboratorio()

    def __str__(self):
        return '\r\n'.join(self.registros)

    def adicionar(self, registro):
        for i, item in enumerate(registro):
            registro[i] = str(item)
        self.registros.append('|'.join(registro))

    def limpar_texto(self, texto, sem_pontuacao=True):
        # Permite letras com acento, números, espaço, ponto, vírgula e ponto e vírgula
        if sem_pontuacao:
            # Permite letras com acento, números e espaço
            regex = r'[^A-Za-z0-9ÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇáéíóúàèìòùâêîôûãõç ]+'
        else:
            regex = r'[^A-Za-z0-9ÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇáéíóúàèìòùâêîôûãõç.,; ]+'
        return re.sub(regex, '', texto)

    def exportar_docentes(self, matriculas=None):
        from pesquisa.models import Projeto as ProjetoPesquisa
        from pesquisa.models import TipoVinculo
        from projetos.models import Projeto as ProjetoExtensao

        if matriculas is None:
            matriculas = []
        registro = []

        # 1 Tipo do registro
        registro.append(30)

        # 2 ID da IES no INEP
        registro.append(self.codigo_mec)

        self.adicionar(registro)

        # Diários de gradução e pós-graduação scrict sensu
        diarios = Diario.objects.filter(ano_letivo__ano=self.ano)
        if self.uos:
            diarios = diarios.filter(turma__curso_campus__diretoria__setor__uo__in=self.uos)
        diarios_graducao = diarios.filter(turma__curso_campus__modalidade__nivel_ensino=NivelEnsino.GRADUACAO)

        professores_diarios = ProfessorDiario.objects.filter(diario__ano_letivo__ano=self.ano)
        professores_diarios = professores_diarios.filter(
            diario__turma__curso_campus__modalidade__nivel_ensino=NivelEnsino.GRADUACAO
        ) | professores_diarios.filter(diario__turma__curso_campus__modalidade__in=(Modalidade.MESTRADO, Modalidade.DOUTORADO))
        if self.uos:
            professores_diarios = professores_diarios.filter(diario__turma__curso_campus__diretoria__setor__uo__in=self.uos)
        if matriculas:
            professores_diarios = professores_diarios.filter(
                professor__vinculo__pessoa_id__in=Servidor.objects.filter(matricula__in=matriculas).values_list('pessoa_fisica_id', flat=True)
            )
        professores = Servidor.objects.exclude(data_inicio_exercicio_na_instituicao__year__gt=self.ano).filter(
            pessoa_fisica_id__in=professores_diarios.values_list('professor__vinculo__pessoa_id', flat=True)
            .order_by('professor__vinculo__pessoa_id')
            .distinct()
        )

        # Docentes que participaram de projetos de pesquisa no ano de referência
        projetos_pesquisa = ProjetoPesquisa.objects.filter(aprovado=True)
        projetos_pesquisa = (
            projetos_pesquisa.filter(inicio_execucao__year=self.ano)
            | projetos_pesquisa.filter(fim_execucao__year=self.ano)
            | projetos_pesquisa.filter(inicio_execucao__year__lt=self.ano, fim_execucao__year__gt=self.ano)
        )

        # Docentes que participaram de projetos de extensão no ano de referência
        projetos_extensao = ProjetoExtensao.objects.filter(aprovado=True)
        projetos_extensao = (
            projetos_extensao.filter(inicio_execucao__year=self.ano)
            | projetos_extensao.filter(fim_execucao__year=self.ano)
            | projetos_extensao.filter(inicio_execucao__year__lt=self.ano, fim_execucao__year__gt=self.ano)
        )

        if self.cpfs:
            professores = professores.filter(pessoa_fisica__cpf__in=self.cpfs)

        if self.amostra:
            professores = professores[0:10]

        if self.tipo == Exportador.DOCENTE:
            cpfs_adicionados = set()
            for servidor in self.task.iterate(professores):
                if servidor.pessoa_fisica.cpf in self.ignorar_cpfs:
                    continue

                registro = []
                cpf = servidor.pessoa_fisica.cpf.replace('.', '').replace('-', '')
                if cpf in cpfs_adicionados:
                    continue
                cpfs_adicionados.add(cpf)

                eh_professor_ensino = diarios_graducao.filter(
                    professordiario__professor__vinculo__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf
                ).exists()
                eh_professor_pesquisa = projetos_pesquisa.filter(
                    participacao__vinculo_pessoa__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf
                ).exists()
                eh_professor_extensao = projetos_extensao.filter(
                    participacao__vinculo_pessoa__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf
                ).exists()
                eh_professor_gestor = (
                    ServidorFuncaoHistorico.objects.filter(servidor__pessoa_fisica__cpf=servidor.pessoa_fisica.cpf)
                    .filter(
                        Q(data_inicio_funcao__year=self.ano)
                        | Q(data_fim_funcao__year=self.ano)
                        | Q(data_inicio_funcao__year__lt=self.ano, data_fim_funcao__year__gt=self.ano)
                    )
                    .exists()
                )

                if not eh_professor_ensino and not eh_professor_pesquisa and not eh_professor_extensao and not eh_professor_gestor:
                    continue

                eh_professor_substituto = professores.filter(
                    situacao__nome__in=('CONT.PROF.SUBSTITUTO', 'CONT.PROF.TEMPORARIO'), pessoa_fisica__cpf=servidor.pessoa_fisica.cpf
                ).exists()
                eh_professor_visitante = professores.filter(
                    situacao__nome='CONTR.PROF.VISITANTE', pessoa_fisica__cpf=servidor.pessoa_fisica.cpf
                ).exists()

                # 1	Tipo do registro		2	Fixo	Numérico	Obrigatório
                registro.append(31)

                # 2	ID do docente na IES		20	Variável	Alfanumérico	Opcional
                registro.append(servidor.matricula)

                # 3	Nome		120	Variável	Alfanumérico	Obrigatório
                registro.append(to_ascii(servidor.pessoa_fisica.nome.upper()))

                # 4	CPF		11	Fixo	Alfanumérico	Obrigatório
                registro.append(cpf)

                # 5	Documento estrangeiro		20	Variável	Alfanumérico	Opcional
                registro.append('')

                # 6	Data de Nascimento		8	Fixo	Data	Obrigatório
                registro.append(servidor.pessoa_fisica.nascimento_data.strftime('%d%m%Y'))

                # 7	Cor/Raça		1	Fixo	Numérico	Obrigatório TODO
                registro.append((servidor.raca.codigo_censup if servidor.raca else None) or 1)

                # 8	Nacionalidade		1	Fixo	Numérico	Obrigatório
                # 1 - Brasileiro 2 - Brasileira - Nascido no exterior ou naturalizado 3 - Estrangeiro
                if servidor.nacionalidade == 1:
                    registro.append(1)
                elif servidor.nacionalidade in (2, 3):
                    registro.append(2)
                else:
                    registro.append(3)

                # 9	País de origem		3	Fixo	Alfanumérico	Obrigatório
                registro.append(servidor.pais_origem and servidor.pais_origem.codigo_censup or 'BRA')

                # 10	UF de nascimento		2	Fixo	Numérico	Opcional
                registro.append('')

                # 11	Município de Nascimento		7	Fixo	Númerico	Condicional
                registro.append('')

                # 12	Deficiência, Transtorno do espectro autista (TEA), altas habilidades ou superdotação		1	Fixo	Numérico	Obrigatório
                # 0 - Não 1 - Sim 2 - Não dispõe da informação
                registro.append(2)

                # 13	Tipo de deficiência cegueira		1	Fixo	Numérico	Condicional
                registro.append('')

                # 14	Tipo de deficiência - Baixa visão		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('')

                # 15	Tipo de deficiência - Visão monocular		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('')

                # 16	Tipo de deficiência surdez		1	Fixo	Numérico	Condicional
                registro.append('')

                # 17	Tipo de deficiência auditiva		1	Fixo	Numérico	Condicional
                registro.append('')

                # 18	Tipo de deficiência física		1	Fixo	Numérico	Condicional
                registro.append('')

                # 19	Tipo de deficiência surdocegueira		1	Fixo	Numérico	Condicional
                registro.append('')

                # 20	Tipo de deficiência intelectual		1	Fixo	Numérico	Condicional
                registro.append('')

                # 21 Tipo de deficiência - Transtorno do espectro autista (TEA)    1    Fixo    Numérico    Condicional
                registro.append('')

                # 22 Tipo de deficiência - Altas habilidades ou superdotação    1    Fixo    Numérico    Condicional
                registro.append('')

                # 23	Atuação do Docente - Ensino		1	Fixo	Numérico	Inteiro	Obrigatório
                registro.append('1' if eh_professor_ensino else '0')

                # 24	Atuação do Docente - Pesquisa		1	Fixo	Numérico	Inteiro	Obrigatório
                registro.append('1' if eh_professor_pesquisa else '0')

                # 25	Atuação do Docente - Extensão		1	Fixo	Numérico	Inteiro	Obrigatório
                registro.append('1' if eh_professor_extensao else '0')

                # 26	Atuação do Docente - Gestão, planejamento e avaliação		1	Fixo	Numérico	Inteiro	Obrigatório
                registro.append('1' if eh_professor_gestor else '0')

                # 27	Bolsa Pesquisa		1	Fixo	Numérico	Inteiro	Condicional
                if eh_professor_pesquisa:
                    eh_professor_pesquisa_bolsista = projetos_pesquisa.filter(
                        participacao__vinculo=TipoVinculo.BOLSISTA, participacao__vinculo_pessoa__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf
                    ).exists()
                    registro.append('1' if eh_professor_pesquisa_bolsista else '0')
                else:
                    registro.append('')

                # 28	Bolsa Extensão		1	Fixo	Numérico	Inteiro	Condicional
                if eh_professor_extensao:
                    eh_professor_extensao_bolsista = projetos_extensao.filter(
                        participacao__vinculo=TipoVinculo.BOLSISTA, participacao__vinculo_pessoa__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf
                    ).exists()
                    registro.append('1' if eh_professor_extensao_bolsista else '0')
                else:
                    registro.append('')

                # 29	Escolaridade		1	Fixo	Numérico	Inteiro	Obrigatório
                # 1 - Sem formação de nível superior
                # 3 - Nível superior sem pós graduação
                # 4 - Especialização
                # 5 - Mestrado
                # 6 - Doutorado

                # verifica casos que professor possui mais de um vínculo
                duplicados = professores.filter(pessoa_fisica__cpf=servidor.pessoa_fisica.cpf).distinct()
                ids_mesma_pessoa = duplicados.values_list('pessoa_fisica_id', flat=True)
                titulacao = 1
                for professor in Professor.objects.filter(titulacao__isnull=False, vinculo__pessoa_id__in=ids_mesma_pessoa).only('titulacao'):
                    if professor.titulacao in ['Doutor', 'Doutora', 'Pós-Doutor', 'Pós-Doutora']:
                        titulacao = 6
                        break
                    elif titulacao < 5 and professor.titulacao in ['Mestre', 'Mestra']:
                        titulacao = 5
                    elif titulacao < 4 and professor.titulacao == 'Especialista':
                        titulacao = 4
                    elif titulacao < 3 and professor.titulacao in ['Graduado', 'Graduada']:
                        titulacao = 3
                registro.append(titulacao)

                # 30	Tipo de vínculo		1	Fixo	Numérico	Inteiro	Opcional (Obrigatório no Censo de 2026)
                """
                1. Servidor público civil ou militar
                2. Empregado com carteira assinada
                3. Empregado com contrato de trabalho temporário
                4. Autônomo
                5. Microempreendedor Individual (MEI)
                6. Empresário Individual
                7. Voluntário
                8. Bolsista
                9. Sem vínculo empregatício por ser membro de congregação, ordem religiosa ou quaisquer outros que a eles se equiparem.
                10. Sem vínculo contratual (cooperação interinstitucional)
                """
                registro.append('1')

                # 31	Tipo de consórcio, acordo ou programa de cooperação do docente sem vínculo contratual com a IES 		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('')

                # 32	A função de conteudista é exercida em contrato específico (distinto do contrato de regência e/ou função de gestão)?		1	Fixo	Numérico	Inteiro	Opcional (Condicional no Censo 2026)
                registro.append('')

                # 33	Tipo de vínculo - Exclusivo conteudista		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('')

                # 34	Tipo de consórcio, acordo ou programa de cooperação do docente sem vínculo contratual com a IES - Exclusivo conteudista 		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('')

                # 35	Regime de trabalho		1	Fixo	Numérico	Inteiro	Condicional
                jornada = 3
                for s in duplicados.select_related('jornada_trabalho').only('jornada_trabalho__nome'):
                    if s.jornada_trabalho.nome == 'DEDICACAO EXCLUSIVA':
                        jornada = 1
                        break
                    elif jornada > 2 and s.jornada_trabalho.nome == '40 HORAS SEMANAIS':
                        jornada = 2
                registro.append(jornada)

                # 36	Carga horária semanal do docente		2	Variável	Numérico	Inteiro	Opcional (Condicional no Censo 2026)
                registro.append(20 if jornada == 3 else 40)

                # 37	Docente foi admitido ou iniciou suas atividades no ano de referência do Censo?		1	Fixo	Numérico	Inteiro	Opcional (Condional no Censo 2026)
                servidor_admitido_ano_anterior = duplicados.filter(data_inicio_exercicio_na_instituicao__year__lt=self.ano).exists()
                registro.append('0' if servidor_admitido_ano_anterior else '1')

                # 38 Docente foi desligado ou encerrou suas atividades no ano de referência do Censo? 1	Fixo Numérico Inteiro Opcional (Condional no Censo 2026)
                servidor_ativo_no_ano = duplicados.filter(
                    Q(data_fim_servico_na_instituicao__isnull=True) | ~Q(data_fim_servico_na_instituicao__year=self.ano)
                ).exists()
                registro.append('0' if servidor_ativo_no_ano else '1')

                # 39	O docente esteve afastado durante o ano de referência do Censo?		1	Fixo	Numérico	Inteiro	Opcional (Condional no Censo 2026)
                qs_afastamentos = ServidorAfastamento.objects.filter(
                    servidor__pessoa_fisica_id__in=ids_mesma_pessoa, quantidade_dias_afastamento__gt=15, cancelado=False
                ).filter(
                    Q(data_inicio__year=self.ano)
                    | Q(data_termino__year=self.ano)
                    | Q(data_inicio__year__lt=self.ano, data_termino__year__gt=self.ano)
                )
                servidor_afastado_no_ano = qs_afastamentos.exists()
                registro.append('1' if servidor_afastado_no_ano else '0')

                # 40	Docente substituto		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('1' if eh_professor_substituto else '0')

                # 41	Docente Visitante		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('1' if eh_professor_visitante else '0')

                # 42	Docente em exercício em 31/12 do ano do censo		1	Fixo	Numérico	Inteiro	Condicional
                registro.append('1' if servidor_ativo_no_ano else '0')

                self.adicionar(registro)

                for codigo_censup in (
                    diarios_graducao.filter(professordiario__professor__vinculo__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf)
                    .values_list('turma__curso_campus__codigo_censup', flat=True)
                    .order_by('turma__curso_campus__codigo_censup')
                    .distinct()
                ):
                    registro32 = []
                    # 1 Tipo do registro
                    registro32.append(32)

                    # 2 Código do curso no INEP
                    registro32.append(codigo_censup)

                    # 3	Docente Regente		1	Fixo	Numérico	Inteiro	Condicional
                    registro32.append('1' if eh_professor_ensino else '0')

                    # 4	Docente Conteudista		1	Fixo	Numérico	Inteiro	Condicional
                    registro32.append('0')

                    # 5	Docente Coordenador		1	Fixo	Numérico	Inteiro	Condicional
                    registro32.append('1' if eh_professor_gestor else '')
                    self.adicionar(registro32)

                if not servidor_admitido_ano_anterior:
                    registro33 = []
                    # 1	Tipo do registro		2	Fixo	Numérico	Inteiro	Condicional
                    registro33.append(33)

                    # 2	Data admissão		8	Fixo	Data	-	Condicional]
                    obj = duplicados.filter(data_inicio_exercicio_na_instituicao__year=self.ano).only('data_inicio_exercicio_na_instituicao').first()
                    data_admissao = obj.data_inicio_exercicio_na_instituicao.strftime('%d%m%Y') if obj else ''
                    registro33.append(data_admissao)

                    self.adicionar(registro33)

                if not servidor_ativo_no_ano:
                    registro34 = []
                    # 1	Tipo do registro		2	Fixo	Numérico	Inteiro	Condicional
                    registro34.append(34)

                    # 2	Data desligamento		8	Fixo	Data	-	Condicional
                    data_desligamento = (
                        duplicados.filter(data_fim_servico_na_instituicao__year=self.ano)
                        .only('data_fim_servico_na_instituicao')
                        .first()
                        .data_fim_servico_na_instituicao
                    )
                    registro34.append(data_desligamento.strftime('%d%m%Y'))

                    self.adicionar(registro34)

                if servidor_afastado_no_ano:
                    for afastamento in qs_afastamentos.only('data_inicio', 'data_termino'):
                        registro35 = []
                        # 1	Tipo do registro		2	Fixo	Numérico	Inteiro	Condicional
                        registro35.append(35)

                        # 2	Início afastamento		8	Fixo	Data	-	Condicional
                        registro35.append(afastamento.data_inicio.strftime('%d%m%Y'))

                        # 3	Fim afastamento		8	Fixo	Data	-	Condicional
                        data_fim = afastamento.data_termino.strftime('%d%m%Y') if afastamento.data_termino else ''
                        registro35.append(data_fim)

                        self.adicionar(registro35)

            output = tempfile.NamedTemporaryFile(mode='w', dir=os.path.join(settings.TEMP_DIR), delete=False, suffix='.txt')
            output.write(str(self))
            output.close()
            self.task.finalize('Arquivo gerado com sucesso', '/edu/relatorio_censup/', file_path=output.name)

    def exportar_alunos(self):
        from ae.models import Caracterizacao, ParticipacaoAlimentacao, ParticipacaoPasseEstudantil, ParticipacaoTrabalho
        from estagios.models import PraticaProfissional
        from pesquisa.models import Projeto as ProjetoPesquisa
        from pesquisa.models import TipoVinculo
        from projetos.models import Projeto as ProjetoExtensao

        registro = []

        # 1    Tipo de registro
        registro.append(40)

        # 2    ID da IES no INEP
        registro.append(self.codigo_mec)

        self.adicionar(registro)

        # Alunos que participaram de projetos de extensão no ano de referência
        projetos_extensao = ProjetoExtensao.objects.filter(aprovado=True)
        projetos_extensao = (
            projetos_extensao.filter(inicio_execucao__year=self.ano)
            | projetos_extensao.filter(fim_execucao__year=self.ano)
            | projetos_extensao.filter(inicio_execucao__year__lt=self.ano, fim_execucao__year__gt=self.ano)
        )
        alunos_extensao = projetos_extensao.values_list('participacao__vinculo_pessoa', flat=True).order_by('participacao__vinculo_pessoa').distinct()
        alunos_extensao_bolsitas = (
            alunos_extensao.filter(participacao__vinculo=TipoVinculo.BOLSISTA)
            .values_list('participacao__vinculo_pessoa', flat=True)
            .order_by('participacao__vinculo_pessoa')
            .distinct()
        )

        # Aluno que participaram de projetos de pesquisa no ano de referência
        projetos_pesquisa = ProjetoPesquisa.objects.filter(aprovado=True)
        projetos_pesquisa = (
            projetos_pesquisa.filter(inicio_execucao__year=self.ano)
            | projetos_pesquisa.filter(fim_execucao__year=self.ano)
            | projetos_pesquisa.filter(inicio_execucao__year__lt=self.ano, fim_execucao__year__gt=self.ano)
        )
        alunos_pesquisa = projetos_pesquisa.values_list('participacao__vinculo_pessoa', flat=True).order_by('participacao__vinculo_pessoa').distinct()
        alunos_pesquisa_bolsitas = (
            projetos_pesquisa.filter(participacao__vinculo=TipoVinculo.BOLSISTA)
            .values_list('participacao__vinculo_pessoa', flat=True)
            .order_by('participacao__vinculo_pessoa')
            .distinct()
        )

        # Alunos estagiários
        qs_pratica_profissional = PraticaProfissional.objects.filter(obrigatorio=False, tipo=PraticaProfissional.TIPO_ESTAGIO)
        qs_pratica_profissional = (
            qs_pratica_profissional.filter(data_inicio__year=self.ano)
            | qs_pratica_profissional.filter(data_fim__year=self.ano)
            | qs_pratica_profissional.filter(data_inicio__year__lt=self.ano, data_fim__year__gt=self.ano)
        )
        alunos_estagiarios = qs_pratica_profissional.values_list('aluno', flat=True).order_by('aluno').distinct()
        alunos_estagiarios_remunerados = qs_pratica_profissional.filter(remunerada=True).values_list('aluno', flat=True).order_by('aluno').distinct()

        alunos = Aluno.objects.filter(
            matriz__isnull=False,
            curso_campus__modalidade__nivel_ensino=NivelEnsino.GRADUACAO,
            matriculaperiodo__ano_letivo__ano=self.ano,
            ano_letivo__ano__lte=self.ano,
            pessoa_fisica__cpf__isnull=False,
        ).distinct()

        if self.uos:
            alunos = alunos.filter(curso_campus__diretoria__setor__uo__in=self.uos)

        if self.cpfs:
            alunos = alunos.filter(pessoa_fisica__cpf__in=self.cpfs)

        if self.amostra:
            alunos = alunos.order_by('pessoa_fisica__cpf', '-pk')[0:10]
        else:
            alunos = alunos.order_by('pessoa_fisica__cpf', '-pk')

        if self.tipo == Exportador.ALUNOS:
            ultimo_cpf = None
            ano_cursos = {}
            for aluno in self.task.iterate(alunos):
                if aluno.pessoa_fisica.cpf in self.ignorar_cpfs:
                    continue
                if aluno.dt_conclusao_curso and aluno.dt_conclusao_curso.year != self.ano:
                    continue
                if aluno.curso_campus.diretoria.ead and aluno.polo_id and not aluno.polo.codigo_censup:
                    continue
                if aluno.situacao.pk == SituacaoMatricula.FORMADO and not self.ignorar_data_conclusao:
                    from edu.models import CalendarioAcademico

                    calendario = CalendarioAcademico.objects.filter(
                        tipo=CalendarioAcademico.TIPO_SEMESTRAL,
                        diretoria_id=aluno.curso_campus.diretoria_id,
                        ano_letivo__ano=self.ano - 1,
                        periodo_letivo=2,
                    ).first()
                    if calendario and calendario.data_fim > aluno.dt_conclusao_curso:
                        # ignora alunos formados em data anterior à conclusão do período letivo do ano anterior
                        continue
                cpf = aluno.pessoa_fisica.cpf.replace('.', '').replace('-', '')
                if cpf != ultimo_cpf:
                    ultimo_cpf = cpf
                    ano_cursos = {}
                    registro = []

                    try:
                        dados_rf = aluno.get_dados_receita_federal()
                        nome = to_ascii(dados_rf['Nome'].upper())
                        nascimento = f'{dados_rf["DataNascimento"][6:8]}{dados_rf["DataNascimento"][4:6]}{dados_rf["DataNascimento"][0:4]}'
                    except Exception:
                        nome = to_ascii(aluno.pessoa_fisica.nome_registro.upper())
                        nascimento = aluno.pessoa_fisica.nascimento_data.strftime('%d%m%Y')

                    # 1	Tipo de registro	2	Fixo	Numérico	Obrigatório
                    registro.append(41)

                    # 2	ID do aluno no INEP	12	Fixo	Numérico	Opcional
                    registro.append('')

                    # 3	Nome	120	Variável	Alfanumérico	Obrigatório
                    if not re.search('^[a-zA-Z]+$', nome):
                        nome = to_ascii(aluno.pessoa_fisica.nome_registro.upper())
                    registro.append(nome)

                    # 4	CPF	11	Fixo	Alfanumérico	Obrigatório
                    registro.append(cpf)

                    # 5	Documento de estrangeiro ou passaporte	20	Variável	Alfanumérico	Condicional
                    if aluno.nacionalidade == 'Estrangeira' and not aluno.estrangeiro_sem_passaporte:
                        registro.append(aluno.passaporte)
                    else:
                        registro.append('')

                    # 6 Data de Nascimento	8	Fixo	Data	Obrigatório
                    registro.append(nascimento)

                    # 7	Cor/Raça	1	Fixo	Numérico	Obrigatório
                    raca = ''
                    if aluno.raca:
                        raca = aluno.raca.codigo_censup or ''
                    if not raca:
                        try:
                            raca = aluno.caracterizacao.raca_id and aluno.caracterizacao.raca.codigo_censup or ''
                        except Caracterizacao.DoesNotExist:
                            pass
                    registro.append(raca or 6)

                    # 8	Nacionalidade	1	Fixo	Numérico	Obrigatório
                    if aluno.nacionalidade == 'Estrangeira':
                        registro.append(3)
                    elif aluno.nacionalidade == 'Brasileira - Nascido no exterior ou naturalizado':
                        registro.append(2)
                    else:
                        registro.append(1)

                    # 9	UF de nascimento	2	Fixo	Numérico	Condicional
                    registro.append('')

                    # 10	Município de nascimento	7	Fixo	Numérico	Condicional
                    registro.append('')

                    # 11	País de origem	3	Fixo	Alfanumérico	Obrigatório
                    if aluno.nacionalidade == 'Brasileira' or not aluno.pais_origem_id:
                        registro.append('BRA')
                    else:
                        registro.append(aluno.pais_origem.sigla)

                    deficiencias = aluno.get_deficiencias_censup()
                    altashabilidades = aluno.get_nee_altashabilidades_censup()
                    # 12	Aluno com Deficiência, Transtorno do espectro autista (TEA), altas habilidades ou superdotação	1	Fixo	Numérico	Inteiro	Obrigatório
                    possui_necessidade_especial = deficiencias or altashabilidades
                    if possui_necessidade_especial:
                        registro.append(1)
                    else:
                        registro.append(2)

                    # 13	Tipo de deficiência - Cegueira	1	Fixo	Numérico	Condicional
                    if Deficiencia.CEGUEIRA in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 14	Tipo de deficiência - Baixa visão	1	Fixo	Numérico	Inteiro	Condicional
                    if Deficiencia.BAIXA_VISAO in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 15	Tipo de deficiência - Visão monocular	1	Fixo	Numérico	Inteiro	Condicional
                    if Deficiencia.VISAO_MONOCULAR in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 16	Tipo de deficiência - Surdez	1	Fixo	Numérico	Condicional
                    if Deficiencia.SURDEZ in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 17	Tipo de deficiência - auditiva	1	Fixo	Numérico	Condicional
                    if Deficiencia.DEFICIENCIA_AUDITIVA in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 18	Tipo de deficiência - física	1	Fixo	Numérico	Condicional
                    if Deficiencia.DEFICIENCIA_FISICA in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 19	Tipo de deficiência - Surdocegueira	1	Fixo	Numérico	Condicional
                    if Deficiencia.SURDOCEGUEIRA in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 20	Tipo de deficiência - Intelectual	1	Fixo	Numérico	Condicional
                    if Deficiencia.DEFICIENCIA_INTELECTUAL in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 21    Tipo de deficiência - Transtorno do espectro autista (TEA)    1    Fixo    Numérico    Condicional
                    if Deficiencia.TEA in deficiencias:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 22	Tipo de deficiência - Altas habilidades/ superdotação	1	Fixo	Numérico	Condicional
                    if altashabilidades:
                        registro.append(1)
                    else:
                        registro.append(possui_necessidade_especial and '0' or '')

                    # 23    Tipo de escola que concluiu o Ensino Médio    1    Fixo    Numérico    Obrigatório
                    if aluno.tipo_instituicao_origem == 'Privada':
                        registro.append(0)
                    elif aluno.tipo_instituicao_origem == 'Pública':
                        registro.append(1)
                    else:
                        registro.append(2)

                    self.adicionar(registro)

                qs_matricula_periodo = aluno.matriculaperiodo_set.filter(
                    ano_letivo__ano=self.ano, aluno__curso_campus__codigo_censup__isnull=False
                ).exclude(aluno__curso_campus__codigo_censup='')

                if self.uos:
                    qs_matricula_periodo = qs_matricula_periodo.filter(aluno__curso_campus__diretoria__setor__uo__in=self.uos)

                lista = []
                for mp in qs_matricula_periodo.order_by('-periodo_letivo'):
                    if mp.aluno.curso_campus.codigo_censup in lista:
                        continue

                    if mp.aluno.ano_letivo.ano in ano_cursos:
                        if mp.aluno.curso_campus.codigo_censup in ano_cursos[mp.aluno.ano_letivo.ano]:
                            continue
                        else:
                            ano_cursos[mp.aluno.ano_letivo.ano].append(mp.aluno.curso_campus.codigo_censup)
                    else:
                        ano_cursos[mp.aluno.ano_letivo.ano] = [mp.aluno.curso_campus.codigo_censup]

                    lista.append(mp.aluno.curso_campus.codigo_censup)
                    registro = []

                    # 1	Tipo de registro	2	Fixo	Numérico	Obrigatório
                    registro.append(42)

                    # 2    ID na IES - Identificação única do aluno na IES    20    Variável    Alfanumérico    Opcional
                    registro.append('')

                    # 3	Período de referência	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 4	Código do Curso	12	Variável	Numérico	Obrigatório
                    registro.append(mp.aluno.curso_campus.codigo_censup)

                    # 5	Código do pólo do curso a distância 	12	Variável	Numérico (tabela)	Condicional
                    if mp.aluno.curso_campus.diretoria.ead and mp.aluno.polo_id:
                        registro.append(mp.aluno.polo.codigo_censup)
                    else:
                        registro.append('')

                    # 6	Turno do aluno	1	Fixo	Numérico	Condicional
                    if not mp.aluno.curso_campus.diretoria.ead:
                        if mp.aluno.turno_id == 3:  # Matutino
                            registro.append(1)
                        elif mp.aluno.turno_id == 2:  # Vespertino
                            registro.append(2)
                        elif mp.aluno.turno_id == 1:  # Noturno
                            registro.append(3)
                        else:
                            registro.append(4)
                    else:
                        registro.append('')

                    # 7	Situação de vínculo do aluno ao curso	1	Fixo	Numérico 	Obrigatório
                    ch_prevista = mp.aluno.matriz.get_carga_horaria_total_prevista()
                    ch_pendente = mp.aluno.get_ch_pendente(ano=self.ano)
                    ch_cumprida = ch_prevista - ch_pendente

                    is_formado = mp.aluno.dt_conclusao_curso and mp.aluno.dt_conclusao_curso.year == self.ano
                    id_situacao_censup = ''
                    if (
                        ch_prevista <= ch_cumprida
                        and not mp.aluno.pendencia_tcc
                        and not mp.aluno.pendencia_pratica_profissional
                        and not mp.aluno.pendencia_ch_atividade_complementar
                        and not mp.aluno.pendencia_ch_tcc
                        and not mp.aluno.pendencia_ch_pratica_profissional
                        and not mp.aluno.pendencia_ch_seminario
                        and not mp.aluno.pendencia_ch_eletiva
                        and not mp.aluno.pendencia_ch_optativa
                        and not mp.aluno.pendencia_ch_obrigatoria
                    ):
                        is_formado = True
                        id_situacao_censup = 6
                    elif mp.aluno.situacao.pk == SituacaoMatricula.FALECIDO:
                        id_situacao_censup = 7
                    else:
                        situacao_censup = mp.get_situacao_censup()
                        if situacao_censup == 'Formado':
                            id_situacao_censup = 6
                        elif situacao_censup == 'Cursando':
                            id_situacao_censup = 2
                        elif situacao_censup == 'Matrícula Trancada':
                            id_situacao_censup = 3
                        elif situacao_censup == 'Transferido para outro curso da mesma IES':
                            id_situacao_censup = 5
                        elif situacao_censup == 'Desvinculado do Curso':
                            id_situacao_censup = 4

                    if not is_formado and id_situacao_censup == 6:
                        # se aluno não está formado no ano do censup então não será adicionado
                        continue

                    registro.append(id_situacao_censup)

                    # 8	Curso origem	12	Variável	Numérico	Condicional
                    semestre_ingresso = f'0{mp.aluno.periodo_letivo}{mp.aluno.ano_letivo.ano}'
                    qs_curso_origem = (
                        Aluno.objects.exclude(pk=mp.aluno.pk)
                        .exclude(curso_campus__codigo_censup=mp.aluno.curso_campus.codigo_censup)
                        .filter(
                            pessoa_fisica__cpf=mp.aluno.pessoa_fisica.cpf,
                            curso_campus__modalidade=mp.aluno.curso_campus.modalidade,
                            situacao=SituacaoMatricula.TRANSFERIDO_INTERNO,
                        )
                        .filter(matriculaperiodo__ano_letivo__ano=self.ano)
                        .order_by('-ano_letivo__ano')
                    )
                    qs_matriz_origem = (
                        Aluno.objects.exclude(pk=mp.aluno.pk)
                        .filter(curso_campus__codigo_censup=mp.aluno.curso_campus.codigo_censup)
                        .filter(
                            pessoa_fisica__cpf=mp.aluno.pessoa_fisica.cpf,
                            curso_campus__modalidade=mp.aluno.curso_campus.modalidade,
                            situacao=SituacaoMatricula.TRANSFERIDO_INTERNO,
                        )
                        .filter(matriculaperiodo__ano_letivo__ano=self.ano)
                        .order_by('-ano_letivo__ano')
                    )
                    if qs_curso_origem.exists() and (mp.aluno.forma_ingresso_id and 'transf' in mp.aluno.forma_ingresso.descricao.lower()):
                        registro.append(qs_curso_origem[0].curso_campus.codigo_censup)
                    else:
                        registro.append('')

                    if qs_matriz_origem.exists():
                        semestre_ingresso = f'0{qs_matriz_origem[0].periodo_letivo}{qs_matriz_origem[0].ano_letivo.ano}'

                    # 9	Semestre de conclusão do curso	1	Fixo	Numérico	Condicional
                    if is_formado:
                        registro.append(mp.periodo_letivo)
                    else:
                        registro.append('')

                    # 10	Aluno PARFOR	1	Fixo	Numérico	Condicional
                    if mp.aluno.curso_campus.is_licenciatura():
                        if mp.aluno.convenio_id and mp.aluno.convenio.descricao == 'PARFOR':
                            registro.append(1)
                        else:
                            registro.append(0)
                    else:
                        registro.append('')

                    # 11 Segunda Licenciatura / Formação pedagógica    1 Fixo Numérico Condicional
                    registro.append(mp.aluno.curso_campus.is_licenciatura() and '0' or '')

                    # 12 Tipo - Segunda Licenciatura / Formação pedagógica    1 Fixo Numérico Condicional
                    registro.append('')

                    # 13	Semestre de ingresso no curso	6	Fixo	Numérico	Obrigatório
                    registro.append(semestre_ingresso)

                    # 14	"Forma de ingresso/seleção  - Vestibular"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.VESTIBULAR and 1 or 0)

                    # 15	"Forma de ingresso/seleção  - Enem"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.ENEM and 1 or 0)

                    # 16	"Forma de ingresso/seleção  - Avaliação Seriada"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.AVALIACAO_SERIADA and 1 or 0)

                    # 17	"Forma de ingresso/seleção  - Seleção Simplificada"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.SELECAO_SIMPLIFICADA and 1 or 0)

                    # 18	"Forma de ingresso/seleção  - Egresso BI/LI"	1	Fixo	Numérico	Obrigatório
                    registro.append(0)

                    # 19	"Forma de ingresso/seleção  - PEC-G"	1	Fixo	Numérico	Condicional
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.PEC_G and 1 or 0)

                    # 20	"Forma de ingresso/seleção  - Transferência Ex Officio"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.TRANSFERENCIA_EX_OFICIO and 1 or 0)

                    # 21	"Forma de ingresso/seleção  - Decisão judicial"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.DECISAO_JUDICIAL and 1 or 0)

                    # 22	"Forma de ingresso  - Seleção para Vagas Remanescentes"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.VAGAS_REMANESCENTES and 1 or 0)

                    # 23	"Forma de ingresso  - Seleção para Vagas de Programas Especiais"	1	Fixo	Numérico	Obrigatório
                    registro.append(mp.aluno.forma_ingresso.classificacao_censup == FormaIngresso.PROGRAMAS_ESPECIAIS and 1 or 0)

                    # 24	Mobilidade acadêmica	1	Fixo	Numérico	Condicional
                    is_aluno_intercambista = mp.situacao == SituacaoMatriculaPeriodo.INTERCAMBIO and 1 or 0
                    registro.append(is_aluno_intercambista)

                    # 25	Tipo de mobilidade acadêmica	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 26	Mobilidade acadêmica Nacional - IES destino	12	Variável	Numérico	Condicional
                    registro.append('')

                    # 27	Mobilidade acadêmica Internacional - País destino	3	Fixo	Alfanumérico	Condicional
                    registro.append('')

                    # 28	Financiamento estudantil	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 29	"Financiamento Estudantil Reembolsável - FIES"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 30	"Financiamento Estudantil Reembolsável - Governo Estadual"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 31	"Financiamento Estudantil Reembolsável -Governo Municipal"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 32	"Financiamento Estudantil Reembolsável  - IES"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 33	"Financiamento Estudantil Reembolsável - Entidades externas"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 34	"Tipo de financiamento não reembolsável - ProUni integral"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 35	"Tipo de financiamento não reembolsável - ProUni parcial"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 36	"Tipo de financiamento não reembolsável - Entidades externas"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 37	"Tipo de financiamento não reembolsável - Governo estadual"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 38	"Tipo de financiamento não reembolsável - IES"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 39	"Tipo de financiamento não reembolsável - Governo municipal"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 40	Apoio Social	1	Fixo	Numérico	Obrigatório
                    qs_alimentacao = ParticipacaoAlimentacao.objects.filter(participacao__aluno=mp.aluno)
                    qs_bolsa = ParticipacaoTrabalho.objects.filter(participacao__aluno=mp.aluno)
                    qs_transporte = ParticipacaoPasseEstudantil.objects.filter(participacao__aluno=mp.aluno)
                    possui_apoio_social = qs_alimentacao.exists() or qs_bolsa.exists() or qs_transporte.exists()
                    registro.append(possui_apoio_social and 1 or 0)

                    # 41	"Tipo de apoio social - Alimentação"	1	Fixo	Numérico	Condicional
                    if possui_apoio_social:
                        registro.append(qs_alimentacao.exists() and 1 or 0)
                    else:
                        registro.append('')

                    # 42	"Tipo de apoio social - Moradia"	1	Fixo	Numérico	Condicional
                    if possui_apoio_social:
                        registro.append(0)
                    else:
                        registro.append('')

                    # 43	"Tipo de apoio social - Transporte"	1	Fixo	Numérico	Condicional
                    if possui_apoio_social:
                        registro.append(qs_transporte.exists() and 1 or 0)
                    else:
                        registro.append('')

                    # 44	"Tipo de apoio social - Material didático"	1	Fixo	Numérico	Condicional
                    if possui_apoio_social:
                        registro.append(0)
                    else:
                        registro.append('')

                    # 45	"Tipo de apoio social - Bolsa trabalho"	1	Fixo	Numérico	Condicional
                    if possui_apoio_social:
                        registro.append(qs_bolsa.exists() and 1 or 0)
                    else:
                        registro.append('')

                    # 46	"Tipo de apoio social - Bolsa permanência"	1	Fixo	Numérico	Condicional
                    if possui_apoio_social:
                        registro.append(0)
                    else:
                        registro.append('')

                    # 47	Atividade extracurricular	1	Fixo	Numérico	Obrigatório
                    is_aluno_pesquisa = mp.aluno.pessoa_fisica.pk in alunos_pesquisa
                    is_bolsista_pesquisa = mp.aluno.pessoa_fisica.pk in alunos_pesquisa_bolsitas
                    is_aluno_extensao = mp.aluno.pessoa_fisica.pk in alunos_extensao
                    is_bolsista_extensao = mp.aluno.pessoa_fisica.pk in alunos_extensao_bolsitas
                    is_aluno_estagiario = mp.aluno.pk in alunos_estagiarios
                    if is_aluno_pesquisa or is_aluno_extensao or is_aluno_estagiario:
                        registro.append(1)
                    else:
                        registro.append(0)

                    # 48	"Atividade extracurricular - Pesquisa"	1	Fixo	Numérico	Condicional
                    if is_aluno_pesquisa or is_aluno_extensao or is_aluno_estagiario:
                        registro.append(is_aluno_pesquisa and 1 or 0)
                    else:
                        registro.append('')

                    # 49	"Bolsa/remuneração referente à atividade extracurricular - Pesquisa"	1	Fixo	Numérico	Condicional
                    if is_aluno_pesquisa:
                        registro.append(is_bolsista_pesquisa and 1 or 0)
                    else:
                        registro.append('')

                    # 50	"Atividade extracurricular - Extensão"	1	Fixo	Numérico	Condicional
                    if is_aluno_pesquisa or is_aluno_extensao or is_aluno_estagiario:
                        registro.append(is_aluno_extensao and 1 or 0)
                    else:
                        registro.append('')

                    # 51	"Bolsa/remuneração referente à atividade extracurricular - Extensão"	1	Fixo	Numérico	Condicional
                    if is_aluno_extensao:
                        registro.append(is_bolsista_extensao and 1 or 0)
                    else:
                        registro.append('')

                    # 52	"Atividade extracurricular - Monitoria"	1	Fixo	Numérico	Condicional
                    if is_aluno_pesquisa or is_aluno_extensao or is_aluno_estagiario:
                        registro.append(0)
                    else:
                        registro.append('')

                    # 53	"Bolsa/remuneração referente à atividade extracurricular - Monitoria"	1	Fixo	Numérico	Condicional
                    registro.append('')

                    # 54	"Atividade extracurricular - Estágio não obrigatório"	1	Fixo	Numérico	Condicional
                    if is_aluno_pesquisa or is_aluno_extensao or is_aluno_estagiario:
                        if is_aluno_estagiario:
                            registro.append(1)
                        else:
                            registro.append(0)
                    else:
                        registro.append('')

                    # 55	"Bolsa/remuneração referente à atividade extracurricular - Estágio não obrigatório"	1	Fixo	Numérico	Condicional
                    if is_aluno_pesquisa or is_aluno_extensao or is_aluno_estagiario:
                        if is_aluno_estagiario:
                            registro.append(mp.aluno.pk in alunos_estagiarios_remunerados and 1 or 0)
                        else:
                            registro.append('')
                    else:
                        registro.append('')

                    # 56	Carga horária total do curso por aluno	5	Variável	Numérico	Obrigatório
                    registro.append(ch_prevista)

                    # 57	Carga horária integralizada pelo aluno	5	Variável	Numérico	Obrigatório
                    registro.append(ch_cumprida)

                    # 58	Ingressou por política de ação afirmativa ou por programa diferenciado de destinação de vagas?	1	Fixo	Numérico	Inteiro	Obrigatório
                    forma_ingresso = mp.aluno.forma_ingresso
                    tem_acao_afirmativa = forma_ingresso and forma_ingresso.is_acao_afirmativa_ou_programa_vagas()
                    registro.append(1 if tem_acao_afirmativa else 0)

                    # 59	Tipo de política de ação afirmativa ou programa diferenciado de destinação de vagas?	1	Fixo	Numérico	Inteiro	Condicional
                    tipo_acao = forma_ingresso.get_tipo_politica_acao_afirmativa()
                    registro.append(tipo_acao if tem_acao_afirmativa else '')

                    # 60	Tipo de Ação Afirmativa - Lei de Cotas (Lei nº 12.711 de 2012 e Lei nº 14.723 de 2023)	1	Fixo	Numérico	Inteiro	Condicional
                    is_lei_cotas = bool(tem_acao_afirmativa and tipo_acao == 1)
                    registro.append(forma_ingresso.get_tipo_afirmacao() if is_lei_cotas else '')

                    # 61	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Preto, Pardo e Indígena (PPI)	1	Fixo	Numérico	Inteiro	Condicional
                    is_outras_reservas = bool(tem_acao_afirmativa and tipo_acao == 2)
                    registro.append('0' if is_outras_reservas else '')

                    # 62	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Renda	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 63	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Pessoa com deficiência	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append(forma_ingresso.get_tipo_afirmacao() if is_outras_reservas else '')

                    # 64	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Estudante procedente de escola pública	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 65	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Quilombola	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 66	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Estudante transgênero e/ou travesti	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 67	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Estudante internacional	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 68	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Refugiado, Apátrida ou Portador de visto humanitário	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 69	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Idoso	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 70	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Estudante pertencente a povos e comunidades tradicionais	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 71	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Medalhista em olimpíadas científicas e competições de conhecimento	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 72	Outras reservas de vagas OU Programa diferenciado de destinação de vagas - Outros tipos de reserva de vagas	1	Fixo	Numérico	Inteiro	Condicional
                    registro.append('0' if is_outras_reservas else '')

                    # 73    Justificativa    2    Fixo    Numérico    Condicional
                    from edu.models.censos import RespostaJustificativaCensup

                    justificativa = RespostaJustificativaCensup.objects.filter(
                        aluno_id=mp.aluno.id, justificativa_censup__ano_letivo__ano=self.ano, data_resposta__isnull=False
                    ).first()
                    registro.append(justificativa and justificativa.resposta or '')

                    self.adicionar(registro)

            output = tempfile.NamedTemporaryFile(mode='w', dir=settings.TEMP_DIR, delete=False, suffix='.txt')
            output.write(str(self))
            output.close()
            self.task.finalize('Arquivo gerado com sucesso', '/edu/relatorio_censup/', file_path=output.name)

    def exportar_laboratorio(self):
        registro = []

        # CABEÇALHO DO ARQUIVO - REGISTRO 10
        # 1	Tipo do registro		2	Fixo	Numérico	Inteiro	Obrigatório
        registro.append(10)

        # 2	ID da IES no INEP		12	Variável	Numérico	Inteiro	Obrigatório
        registro.append(self.codigo_mec)
        self.adicionar(registro)

        from edu.models import Laboratorio

        qs_laboratorio = (
            Laboratorio.objects.filter(ativo=True)
            .exclude(sala__predio__uo__codigo_censup__isnull=True)
            .exclude(sala__predio__uo__codigo_censup='')
            .select_related('sala', 'sala__predio__uo__municipio')
        )
        if self.uos:
            qs_laboratorio = qs_laboratorio.filter(sala__predio__uo__in=self.uos)
        for laboratorio in self.task.iterate(qs_laboratorio.distinct()):
            qs_diario = (
                Diario.objects.filter(
                    Q(local_laboratorio=laboratorio.sala_id) | Q(local_aula_id=laboratorio.sala_id) | Q(locais_aula_secundarios=laboratorio.sala_id)
                )
                .filter(turma__curso_campus__ativo=True)
                .distinct()
            )
            qs_diarios_graduacao = qs_diario.filter(turma__matriz__nivel_ensino=NivelEnsino.GRADUACAO, ano_letivo__ano=self.ano)
            teve_aula_graduacao = qs_diarios_graduacao.exists()

            from pesquisa.models import Projeto as ProjetoPesquisa
            from pesquisa.models import ProjetoLaboratorioPesquisa

            ids_pp = ProjetoLaboratorioPesquisa.objects.filter(tipo='Pesquisa', laboratorio__sala_id=laboratorio.sala_id).values_list(
                'id_do_projeto', flat=True
            )
            qs_projeto_pesquisa = ProjetoPesquisa.objects.filter(id__in=ids_pp, edital__divulgacao_selecao__year=self.ano)
            ids_alunos_pesquisa = (
                qs_projeto_pesquisa.filter(participacao__vinculo_pessoa__tipo_relacionamento__model='aluno')
                .values_list('participacao__vinculo_pessoa__id_relacionamento', flat=True)
                .distinct()
            )
            qs_alunos_pesquisa = Aluno.objects.filter(id__in=ids_alunos_pesquisa, curso_campus__modalidade__nivel_ensino_id=NivelEnsino.GRADUACAO)
            teve_aula_pesquisa = qs_alunos_pesquisa.exists()

            from projetos.models import Edital as EditalExtensao
            from projetos.models import Projeto as ProjetoExtensao

            ids_pe = ProjetoLaboratorioPesquisa.objects.filter(tipo='Pesquisa', laboratorio__sala_id=laboratorio.sala_id).values_list(
                'id_do_projeto', flat=True
            )
            qs_projeto_extensao = ProjetoExtensao.objects.filter(id__in=ids_pe).filter(
                Q(edital__divulgacao_selecao__year=self.ano) | Q(edital__tipo_fomento=EditalExtensao.FOMENTO_EXTERNO)
            )
            ids_alunos_extensao = (
                qs_projeto_extensao.filter(participacao__vinculo_pessoa__tipo_relacionamento__model='aluno')
                .values_list('participacao__vinculo_pessoa__id_relacionamento', flat=True)
                .distinct()
            )
            qs_alunos_extensao = Aluno.objects.filter(id__in=ids_alunos_extensao, curso_campus__modalidade__nivel_ensino_id=NivelEnsino.GRADUACAO)
            teve_aula_extensao = qs_alunos_extensao.exists()

            # REGISTRO DO LABORATORIO - REGISTRO 11
            registro = []
            # 1	Tipo do registro		2	Fixo	Numérico	Inteiro	Obrigatório
            registro.append(11)

            # 2	Nome do laboratório na IES		200	Variável	Alfanumérico	-	Obrigatório
            registro.append(self.limpar_texto(laboratorio.nome))

            # 3	Registro do Laboratório na IES		14	Variável	Alfanumérico	-	Opcional
            registro.append(laboratorio.id)

            # 4	O laboratório esteve ativo no ano de 2025?		1	Fixo	Numérico	Inteiro	Obrigatório
            laboratorio_ativo = teve_aula_graduacao or teve_aula_pesquisa or teve_aula_extensao
            registro.append(1 if laboratorio_ativo else 0)

            # 5	Descrição das atividades do laboratório		2000	Variável	Alfanumérico	-	Opcional
            registro.append(self.limpar_texto(laboratorio.descricao) or '')

            # 6	Palavras-Chave		100	Variável	Alfanumérico	-	Opcional
            registro.append(
                ' '.join(self.limpar_texto(laboratorio.palavras_chave, sem_pontuacao=True).split(' ')[0:3]) if laboratorio.palavras_chave else ''
            )

            # 7	O laboratório é de informática?		1	Fixo	Numérico	Inteiro	Opcional
            registro.append(1 if laboratorio.laboratorio_informatica else 0)

            if laboratorio.area_conhecimento_1 or laboratorio.area_conhecimento_2:
                # 8	Área de conhecimento do laboratório. Ciências Exatas e da Terra		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(
                    1 if Laboratorio.AREA_CONHECIMENTO_EXATAS in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0
                )

                # 9	Área de conhecimento do laboratório. Ciências Biológicas		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(
                    1 if Laboratorio.AREA_CONHECIMENTO_BIOLOGICAS in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0
                )

                # 10	Área de conhecimento do laboratório. Engenharias		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(
                    1 if Laboratorio.AREA_CONHECIMENTO_ENGENHARIAS in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0
                )

                # 11	Área de conhecimento do laboratório.  Ciência da Saúde		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if Laboratorio.AREA_CONHECIMENTO_SAUDE in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0)

                # 12	Área de conhecimento do laboratório. Ciências Agrárias		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(
                    1 if Laboratorio.AREA_CONHECIMENTO_AGRARIAS in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0
                )

                # 13	Área de conhecimento do laboratório. Ciências Sociais Aplicadas		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(
                    1 if Laboratorio.AREA_CONHECIMENTO_SOCIAIS in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0
                )

                # 14	Área de conhecimento do laboratório. Ciências Humanas		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(
                    1 if Laboratorio.AREA_CONHECIMENTO_HUMANAS in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0
                )

                # 15	Área de conhecimento do laboratório. Linguística, Letras e Artes		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(
                    1 if Laboratorio.AREA_CONHECIMENTO_LINGUISTICA in [laboratorio.area_conhecimento_1, laboratorio.area_conhecimento_1] else 0
                )
            else:
                registro.append('')
                registro.append('')
                registro.append('')
                registro.append('')
                registro.append('')
                registro.append('')
                registro.append('')
                registro.append('')

            # 16	O laboratório é itinerante?		1	Fixo	Numérico	Inteiro	Opcional
            registro.append(0)

            # 17	Além dos alunos de graduação, houve outros estudantes que utilizaram o laboratório durante o ano letivo de 2024?		1	Fixo	Numérico	Inteiro	Opcional
            registro.append(
                1 if qs_diario.filter(ano_letivo__ano=self.ano).exclude(turma__matriz__nivel_ensino=NivelEnsino.GRADUACAO).exists() else 0
            )

            if laboratorio_ativo:
                # 18	Durante o ano letivo de 2025, o laboratório foi utilizado para a finalidade de Ensino?		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if teve_aula_graduacao else 0)

                # 19	Durante o ano letivo de 2025, o laboratório foi utilizado para a finalidade de Pesquisa?		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if teve_aula_pesquisa else 0)

                # 20	Durante o ano letivo de 2025, o laboratório foi utilizado para a finalidade de Extensão?		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if teve_aula_extensao else 0)
            else:
                registro.append('')
                registro.append('')
                registro.append('')

            plano = laboratorio.execucaoplanolaboratorio_set.filter(ano__ano=self.ano).first()
            if laboratorio_ativo and plano is None:
                registro.append(0)
                registro.append(0)
                registro.append(0)
                registro.append(0)
            elif laboratorio_ativo:
                # 21	Durante o ano letivo de 2025, o laboratório executou plano, procedimento ou protocolo formal de Política de acesso e agendamento?		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if plano.plano_politica_acesso else 0)

                # 22	Durante o ano letivo de 2025, o laboratório executou plano, procedimento ou protocolo formal de Manutenção?		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if plano.plano_manutencao else 0)

                # 23	Durante o ano letivo de 2025, o laboratório executou plano, procedimento ou protocolo formal de Gerenciamento de riscos?		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if plano.plano_riscos else 0)

                # 24	Durante o ano letivo de 2025, o laboratório executou plano, procedimento ou protocolo formal de gerenciamento de resíduos?		1	Fixo	Numérico	Inteiro	Opcional
                registro.append(1 if plano.plano_residuos else 0)
            else:
                registro.append('')
                registro.append('')
                registro.append('')
                registro.append('')

            # 25	O laboratório está localizado em algum local de oferta da IES?		1	Fixo	Numérico	Inteiro	Condicional
            registro.append('1')

            # 26	Código do local de oferta		12	Variável	Numérico (tabela)	Inteiro	Condicional
            registro.append(laboratorio.sala.predio.uo.codigo_censup)

            # 27	Código da UF do laboratório		2	Fixo	Numérico	Inteiro	Condicional
            # registro.append(24)
            registro.append('')

            # 28	Código do município do laboratório		7	Fixo	Numérico	Inteiro	Condicional
            # cidade = Cidade.objects.filter(nome__iexact=laboratorio.sala.predio.uo.municipio.nome, estado_id=24).first()
            # registro.append(cidade.codigo if cidade else '')
            registro.append('')

            self.adicionar(registro)

            if laboratorio_ativo:
                codigos = set()
                if teve_aula_graduacao:
                    for cod_curso in qs_diarios_graduacao.values_list('turma__curso_campus__codigo_censup', flat=True).distinct():
                        codigos.add(cod_curso)
                if teve_aula_extensao:
                    for cod_curso in (
                        qs_alunos_extensao.exclude(curso_campus__codigo_censup__in=codigos)
                        .values_list('curso_campus__codigo_censup', flat=True)
                        .distinct()
                    ):
                        codigos.add(cod_curso)
                if teve_aula_pesquisa:
                    for cod_curso in (
                        qs_alunos_pesquisa.exclude(curso_campus__codigo_censup__in=codigos)
                        .values_list('curso_campus__codigo_censup', flat=True)
                        .distinct()
                    ):
                        codigos.add(cod_curso)

                for codigo in codigos:
                    # REGISTRO DO LABORATORIO VÍNCULO CURSO - REGISTRO 12
                    registro = []
                    # 1	Tipo do registro		2	Fixo	Numérico	Inteiro	Condicional
                    registro.append(12)
                    # 2	Código do curso no INEP		12	Variável	Numérico	Inteiro	Condicional
                    registro.append(codigo)
                    self.adicionar(registro)
            else:
                # REGISTRO DO LABORATORIO VÍNCULO CURSO - REGISTRO 12
                registro = []
                # 1	Tipo do registro		2	Fixo	Numérico	Inteiro	Condicional
                registro.append(12)
                # 2	Código do curso no INEP		12	Variável	Numérico	Inteiro	Condicional
                registro.append('')
                self.adicionar(registro)

        output = tempfile.NamedTemporaryFile(mode='w', dir=settings.TEMP_DIR, delete=False, suffix='.txt')
        output.write(str(self))
        output.close()
        self.task.finalize('Arquivo gerado com sucesso', '/edu/relatorio_censup/', file_path=output.name)
