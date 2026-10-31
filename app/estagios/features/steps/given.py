from behave import given
from comum.models import Ano
from edu.models import (
    Turno,
    Aluno,
    SituacaoMatricula,
    Matriz,
    Componente,
    TipoComponente,
    ComponenteCurricular,
    EquivalenciaComponenteQAcademico,
    MatriculaDiarioResumida,
    MatriculaDiario,
    MatrizCurso,
    NivelEnsino,
    CursoCampus,
    Diretoria,
    Nucleo,
    Professor,
    Modalidade,
    EstruturaCurso,
    MatriculaPeriodo,
    SituacaoMatriculaPeriodo,
    Estado,
    Cidade,
)
from estagios.models import TipoRemuneracao
from rh.models import Setor, PessoaJuridica, Servidor
from datetime import datetime, date


@given('os dados básicos para os estágios')
def step_dados_basicos_estagios(context):
    Turno.objects.get_or_create(id='6', descricao='Diurno')
    Turno.objects.get_or_create(id='1', descricao='Noturno')
    ano_int = datetime.now().year - 2
    ano = Ano.objects.get_or_create(ano=str(ano_int))[0]
    situacao = SituacaoMatricula.objects.get_or_create(descricao='Matriculado', ativo=True)[0]

    diretoria = Diretoria.objects.get_or_create(setor=Setor.objects.suap_ativos().get(sigla='DIAC/CEN'))[0]

    modalidade = Modalidade.objects.get_or_create(descricao='Engenharia', id=Modalidade.ENGENHARIA)[0]
    estrutura = EstruturaCurso.objects.get_or_create(
        descricao='Estrutura',
        ativo=True,
        tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO,
        criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
    )[0]

    curso = CursoCampus.objects.get_or_create(
        descricao='Curso',
        descricao_historico='Curso',
        ano_letivo=ano,
        periodo_letivo=1,
        data_inicio=date.today(),
        ativo=True,
        codigo='0981',
        modalidade=modalidade,
        # turno=turno,
        # area=area.pk,
        # eixo=eixo.pk,
        # area_capes=area_capes.pk,
        # periodicidade=CursoCampus.PERIODICIDADE_LIVRE,
        diretoria=diretoria,
        emite_diploma=True,
    )[0]

    tipo_componente = TipoComponente.objects.get_or_create(descricao='TESTE')[0]

    componente01 = Componente.objects.get_or_create(
        descricao='Componente 01 para teste',
        descricao_historico='Componente 01 para teste',
        abreviatura='C01T',
        tipo=tipo_componente,
        diretoria=diretoria,
        nivel_ensino=NivelEnsino.objects.get_or_create(pk=NivelEnsino.GRADUACAO, descricao='Graduação')[0],
        ativo=True,
        ch_hora_relogio=5,
        ch_hora_aula=7,
        ch_qtd_creditos=2,
    )[0]
    componente02 = Componente.objects.get_or_create(
        descricao='Componente 02 para teste',
        descricao_historico='Componente 02 para teste',
        abreviatura='C02T',
        tipo=tipo_componente,
        diretoria=diretoria,
        nivel_ensino=NivelEnsino.objects.get_or_create(pk=NivelEnsino.GRADUACAO, descricao='Graduação')[0],
        ativo=True,
        ch_hora_relogio=5,
        ch_hora_aula=7,
        ch_qtd_creditos=2,
    )[0]
    componente03 = Componente.objects.get_or_create(
        descricao='Componente 03 para teste',
        descricao_historico='Componente 03 para teste',
        abreviatura='C03T',
        tipo=tipo_componente,
        diretoria=diretoria,
        nivel_ensino=NivelEnsino.objects.get_or_create(pk=NivelEnsino.GRADUACAO, descricao='Graduação')[0],
        ativo=True,
        ch_hora_relogio=5,
        ch_hora_aula=6,
        ch_qtd_creditos=2,
    )[0]
    tcc = Componente.objects.get_or_create(
        descricao='Trabalho de Conclusão de Curso',
        descricao_historico='Trabalho de Conclusão de Curso',
        abreviatura='TCC',
        tipo=tipo_componente,
        diretoria=diretoria,
        nivel_ensino=NivelEnsino.objects.get_or_create(pk=NivelEnsino.GRADUACAO, descricao='Graduação')[0],
        ativo=True,
        ch_hora_relogio=10,
        ch_hora_aula=10,
        ch_qtd_creditos=2,
    )[0]

    matriz = Matriz.objects.get_or_create(
        descricao='Matriz',
        ano_criacao=ano,
        periodo_criacao=1,
        data_inicio=datetime.now(),
        data_fim=None,
        ativo=True,
        estrutura=estrutura,
        qtd_periodos_letivos=3,
        ch_componentes_obrigatorios=20,
        ch_componentes_optativos=0,
        ch_componentes_eletivos=0,
        ch_seminarios=0,
        ch_componentes_tcc=10,
        ch_atividades_complementares=0,
        ch_pratica_profissional=0,
        ch_atividades_aprofundamento=0,
        ch_atividades_extensao=0,
        ch_pratica_como_componente=0,
        ch_visita_tecnica=0,
    )[0]

    nucleo = Nucleo.objects.get_or_create(descricao='Núcleo Teste')[0]

    ComponenteCurricular.objects.get_or_create(
        matriz=matriz,
        componente=componente01,
        periodo_letivo=1,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        nucleo=nucleo,
        qtd_avaliacoes=2,
        ch_presencial=7,
        ch_pratica=2,
    )
    ComponenteCurricular.objects.get_or_create(
        matriz=matriz,
        componente=componente02,
        periodo_letivo=2,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        nucleo=nucleo,
        qtd_avaliacoes=2,
        ch_presencial=7,
        ch_pratica=2,
    )
    ComponenteCurricular.objects.get_or_create(
        matriz=matriz,
        componente=componente03,
        periodo_letivo=3,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        nucleo=nucleo,
        qtd_avaliacoes=2,
        ch_presencial=6,
        ch_pratica=2,
    )
    ComponenteCurricular.objects.get_or_create(
        matriz=matriz,
        componente=tcc,
        periodo_letivo=1,
        tipo=ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
        nucleo=nucleo,
        qtd_avaliacoes=1,
        ch_presencial=10,
        ch_pratica=5,
    )

    # Cria aluno novato, que não cumpre requisitos para ser estagiário.
    aluno_novato = Aluno.objects.filter(matricula='20201000000001')
    if aluno_novato.exists():
        aluno_novato = aluno_novato[0]
        aluno_novato.ano_letivo = ano
        aluno_novato.periodo_letivo = 1
        aluno_novato.situacao = situacao
        aluno_novato.ano_let_prev_conclusao = datetime.now().year
        aluno_novato.matriz = matriz
        aluno_novato.curso_campus = curso
        aluno_novato.save()
        MatrizCurso.objects.get_or_create(matriz=matriz, curso_campus=curso)

    MatriculaPeriodo.objects.get_or_create(
        aluno=aluno_novato,
        ano_letivo=Ano.objects.get_or_create(ano=ano_int)[0],
        periodo_letivo=1,
        periodo_matriz=1,
        situacao=SituacaoMatriculaPeriodo.objects.get_or_create(id=SituacaoMatriculaPeriodo.MATRICULADO)[0],
    )

    # Cria aluno que possui todos os requisitos para ser estagiário.
    aluno_estagio = Aluno.objects.filter(matricula='20191101011021')
    if aluno_estagio.exists():
        aluno_estagio = aluno_estagio[0]
        aluno_estagio.ano_letivo = ano
        aluno_estagio.periodo_letivo = 1
        aluno_estagio.situacao = situacao
        aluno_estagio.ano_let_prev_conclusao = datetime.now().year
        aluno_estagio.matriz = matriz
        aluno_estagio.curso_campus = curso
        aluno_estagio.save()
        MatrizCurso.objects.get_or_create(matriz=matriz, curso_campus=curso)

    mp1 = MatriculaPeriodo.objects.get_or_create(
        aluno=aluno_estagio,
        ano_letivo=Ano.objects.get_or_create(ano=ano_int)[0],
        periodo_letivo=1,
        periodo_matriz=1,
        situacao=SituacaoMatriculaPeriodo.objects.get_or_create(id=SituacaoMatriculaPeriodo.APROVEITA_MODULO)[0],
    )[0]

    mp2 = MatriculaPeriodo.objects.get_or_create(
        aluno=aluno_estagio,
        ano_letivo=Ano.objects.get_or_create(ano=ano_int)[0],
        periodo_letivo=2,
        periodo_matriz=2,
        situacao=SituacaoMatriculaPeriodo.objects.get_or_create(id=SituacaoMatriculaPeriodo.APROVEITA_MODULO)[0],
    )[0]

    mp3 = MatriculaPeriodo.objects.get_or_create(
        aluno=aluno_estagio,
        ano_letivo=Ano.objects.get_or_create(ano=ano_int + 1)[0],
        periodo_letivo=3,
        periodo_matriz=3,
        situacao=SituacaoMatriculaPeriodo.objects.get_or_create(id=SituacaoMatriculaPeriodo.MATRICULADO, descricao='Matriculado')[0],
    )[0]

    MatriculaDiarioResumida.objects.get_or_create(
        matricula_periodo=mp1,
        situacao=MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
        frequencia=100,
        media_final_disciplina=90,
        equivalencia_componente=EquivalenciaComponenteQAcademico.objects.get_or_create(
            q_academico=1, sigla='C01', descricao='QACAD C01', carga_horaria=7, componente=componente01
        )[0],
    )
    MatriculaDiarioResumida.objects.get_or_create(
        matricula_periodo=mp2,
        situacao=MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
        frequencia=100,
        media_final_disciplina=90,
        equivalencia_componente=EquivalenciaComponenteQAcademico.objects.get_or_create(
            q_academico=2, sigla='C02', descricao='QACAD C02', carga_horaria=7, componente=componente02
        )[0],
    )
    MatriculaDiarioResumida.objects.get_or_create(
        matricula_periodo=mp3,
        situacao=MatriculaDiario.SITUACAO_APROVADO,
        frequencia=85,
        equivalencia_componente=EquivalenciaComponenteQAcademico.objects.get_or_create(
            q_academico=3, sigla='C03', descricao='QACAD C03', carga_horaria=6, componente=componente03
        )[0],
    )

    PessoaJuridica.objects.get_or_create(nome='BANCO DO BRASIL SA', nome_fantasia='Banco do Brasil', cnpj='00.000.000/0001-91')

    servidor = Servidor.objects.filter(matricula='102003')[0]
    if servidor:
        servidor.eh_docente = True
        servidor.save()
        Professor.objects.get_or_create(vinculo=servidor.get_vinculo())
        curso.coordenador = servidor.get_vinculo()
        curso.save()

    servidor2 = Servidor.objects.filter(matricula='102004')[0]
    if servidor2:
        servidor2.eh_docente = True
        servidor2.save()
        Professor.objects.get_or_create(vinculo=servidor2.get_vinculo())

    TipoRemuneracao.objects.get_or_create(descricao='Bolsa')

    estado = Estado.objects.get_or_create(nome='Estado')[0]
    Cidade.objects.get_or_create(nome='Cidade', estado=estado)
