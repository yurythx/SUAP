import copy
import datetime
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.models import Permission

from comum.models import Ano
from comum.tests.factories import AnoFactory
from edu.tests.factories import NivelEnsinoFactory, SituacaoMatriculaFactory
from edu.models import (
    Aluno,
    Aula,
    CalendarioAcademico,
    Componente,
    ComponenteCurricular,
    ConfiguracaoAvaliacao,
    CursoCampus,
    Diario,
    Diretoria,
    EstruturaCurso,
    HorarioCampus,
    ItemConfiguracaoAvaliacao,
    MaterialAula,
    MaterialDiario,
    MatriculaDiario,
    MatriculaPeriodo,
    Matriz,
    MatrizCurso,
    MensagemEntrada,
    Modalidade,
    NivelEnsino,
    Nucleo,
    Professor,
    ProfessorDiario,
    RegistroLeitura,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    TipoComponente,
    TipoProfessorDiario,
    TopicoDiscussao,
    Trabalho,
    Turma,
    Turno,
)
from edu.models.professores import ConfiguracaoDadosDocentes
from rh.models import PessoaFisica, Servidor, Setor, UnidadeOrganizacional


def _inserir_diario_via_sql(d: SimpleNamespace) -> Diario:
    """Insere o ``Diario`` via SQL cru para driblar efeitos colaterais de ``Diario.save()``.

    ``save()`` busca ``ConfiguracaoAvaliacao`` pk=1 (oculta/inacessível no ambiente de
    teste), então mockamos a busca e inserimos a linha diretamente.
    """
    from django.db import connection

    with (
        mock.patch('edu.models.diarios.ConfiguracaoAvaliacao.objects.get', return_value=d.config_template),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
                INSERT INTO edu_diario (
                    turma_id, componente_curricular_id, ano_letivo_id, periodo_letivo,
                    situacao, horario_campus_id, turno_id, estrutura_curso_id, calendario_academico_id,
                    percentual_minimo_ch, quantidade_vagas,
                    posse_etapa_1, posse_etapa_2, posse_etapa_3, posse_etapa_4, posse_etapa_5,
                    segundo_semestre, integracao_com_moodle, ignorar_choque_horario_renovacao_matricula,
                    possui_segunda_oferta, search_fields_optimized
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                ) RETURNING id
             """,
            [
                d.turma.id,
                d.componente_curricular.id,
                d.ano_2013.id,
                1,
                Diario.SITUACAO_ABERTO,
                d.horario_campus.id,
                d.turno.id,
                d.estrutura.id,
                d.calendario.id,
                75,
                0,
                Diario.POSSE_PROFESSOR,
                Diario.POSSE_PROFESSOR,
                Diario.POSSE_PROFESSOR,
                Diario.POSSE_PROFESSOR,
                Diario.POSSE_PROFESSOR,
                False,
                False,
                False,
                False,
                '',
            ],
        )
        diario_id = cursor.fetchone()[0]

    return Diario.objects.get(id=diario_id)


@pytest.fixture
def dados_ensino(servidor_a) -> SimpleNamespace:
    """Monta o grafo completo de um diário (curso, matriz, aluno, professor, aula...).

    Substitui o antigo ``setUpTestData``; é function-scoped (cada teste tem dados frescos
    revertidos pela transação) e devolve um ``SimpleNamespace`` com os objetos.

    Do substrato usa só o ``servidor_a`` (que vira o professor do diário); o resto do que
    vinha do ``suap_data`` eram tabelas-tipo (ano, situações, nível de ensino), agora
    criadas por factory.
    """
    d = SimpleNamespace()

    d.ano_2013 = AnoFactory(ano=2013)
    d.situacao_matriculado_periodo = SituacaoMatriculaPeriodo.objects.get_or_create(
        id=SituacaoMatriculaPeriodo.MATRICULADO, defaults={'descricao': 'Matriculado'}
    )[0]
    d.situacao_matricula = SituacaoMatriculaFactory()

    d.turno, _ = Turno.objects.get_or_create(descricao='Matutino')

    d.setor, _ = Setor.objects.get_or_create(nome='Setor Teste API', defaults={'sigla': 'STAPI'})
    d.uo, _ = UnidadeOrganizacional.objects.get_or_create(nome='Campus Teste API', defaults={'sigla': 'CTAPI', 'setor': d.setor})

    d.setor.refresh_from_db()
    d.horario_campus = HorarioCampus.objects.create(descricao='Horário Padrão', uo=d.uo)
    d.diretoria = Diretoria.objects.create(setor=d.setor)

    d.calendario = CalendarioAcademico.objects.create(
        descricao='Calendário 2013',
        tipo=CalendarioAcademico.TIPO_SEMESTRAL,
        ano_letivo=d.ano_2013,
        periodo_letivo=1,
        data_inicio=datetime.date(2013, 1, 1),
        data_fim=datetime.date(2013, 6, 30),
        data_fechamento_periodo=datetime.date(2013, 7, 15),
        qtd_etapas=CalendarioAcademico.QTD_ETAPA_2,
        data_inicio_etapa_1=datetime.date(2013, 1, 1),
        data_fim_etapa_1=datetime.date(2013, 3, 31),
        data_inicio_etapa_2=datetime.date(2013, 4, 1),
        data_fim_etapa_2=datetime.date(2013, 6, 30),
    )

    d.estrutura = EstruturaCurso.objects.create(
        descricao='Estrutura Teste',
        tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_CREDITO,
        criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
        media_aprovacao_sem_prova_final=70,
        media_evitar_reprovacao_direta=20,
        media_aprovacao_avaliacao_final=50,
    )

    d.tipo_componente, _ = TipoComponente.objects.get_or_create(descricao='Disciplina')
    d.nivel_ensino = NivelEnsinoFactory(id=NivelEnsino.GRADUACAO, descricao='Graduação')

    d.componente = Componente.objects.create(
        descricao='Matemática',
        sigla='MAT',
        tipo=d.tipo_componente,
        diretoria=d.diretoria,
        nivel_ensino=d.nivel_ensino,
        ch_hora_relogio=60,
        ch_hora_aula=80,
        ch_qtd_creditos=4,
    )

    d.matriz = Matriz.objects.create(
        descricao='Matriz Teste',
        estrutura=d.estrutura,
        ano_criacao=d.ano_2013,
        data_inicio=datetime.date(2013, 1, 1),
        qtd_periodos_letivos=2,
        ch_componentes_obrigatorios=100,
        ch_componentes_optativos=0,
        ch_componentes_eletivos=0,
        ch_seminarios=0,
        ch_pratica_profissional=0,
        ch_atividades_complementares=0,
        ch_atividades_aprofundamento=0,
        ch_componentes_tcc=0,
        ch_pratica_como_componente=0,
        ch_visita_tecnica=0,
    )

    d.modalidade, _ = Modalidade.objects.get_or_create(descricao='Modalidade Teste', nivel_ensino=d.nivel_ensino)

    d.curso = CursoCampus.objects.create(descricao='Curso Teste', diretoria=d.diretoria, modalidade=d.modalidade)

    MatrizCurso.objects.create(matriz=d.matriz, curso_campus=d.curso)

    d.pessoa_fisica_aluno = PessoaFisica.objects.create(nome='Aluno Teste', nascimento_data=datetime.date(2000, 1, 1), sexo='M', cpf='736.736.736-61')
    d.aluno = Aluno.objects.create(
        pessoa_fisica=d.pessoa_fisica_aluno,
        matricula='20201010101',
        ano_letivo=d.ano_2013,
        periodo_letivo=1,
        situacao=d.situacao_matricula,
        curso_campus=d.curso,
        matriz=d.matriz,
    )
    d.user_aluno = d.aluno.get_user()
    d.user_aluno.set_password('123')
    d.user_aluno.save()

    d.matricula_periodo = MatriculaPeriodo.objects.create(
        aluno=d.aluno, ano_letivo=d.ano_2013, periodo_letivo=1, situacao=d.situacao_matriculado_periodo
    )

    d.nucleo, _ = Nucleo.objects.get_or_create(descricao='Núcleo Comum')

    d.componente_curricular = ComponenteCurricular.objects.create(
        matriz=d.matriz,
        componente=d.componente,
        periodo_letivo=1,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        qtd_avaliacoes=2,
        nucleo=d.nucleo,
        ch_presencial=60,
        ch_pratica=0,
        optativo=False,
    )

    d.turma = Turma.objects.create(
        codigo='20131.1.01',
        curso_campus=d.curso,
        ano_letivo=d.ano_2013,
        periodo_letivo=1,
        turno=d.turno,
        periodo_matriz=1,
        matriz=d.matriz,
    )

    d.config_template = ConfiguracaoAvaliacao.objects.create(forma_calculo=ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ARITMETICA, etapa='1')
    ItemConfiguracaoAvaliacao.objects.create(
        configuracao_avaliacao=d.config_template, tipo=ItemConfiguracaoAvaliacao.TIPO_PROVA, sigla='N1', peso=10, nota_maxima=100
    )

    d.diario = _inserir_diario_via_sql(d)

    d.matricula_diario = MatriculaDiario.objects.create(
        matricula_periodo=d.matricula_periodo, diario=d.diario, situacao=MatriculaDiario.SITUACAO_CURSANDO
    )

    d.servidor = servidor_a
    # portal-professores filtra/ordena pelo e-mail institucional do servidor.
    Servidor.objects.filter(pk=d.servidor.pk).update(email_institucional='professor.admin@ifrn.edu.br')
    d.servidor.refresh_from_db()
    d.vinculo_servidor = d.servidor.get_vinculo()
    d.user = d.servidor.get_user()
    d.user_professor = d.user
    permission = Permission.objects.get(codename='pode_sincronizar_dados', content_type__app_label='edu')
    d.user_professor.user_permissions.add(permission)
    d.professor = Professor.objects.create(vinculo=d.vinculo_servidor)

    d.tipo_professor_diario, _ = TipoProfessorDiario.objects.get_or_create(descricao='Principal')

    d.professor_diario = ProfessorDiario.objects.create(professor=d.professor, diario=d.diario, tipo=d.tipo_professor_diario, ativo=True)

    d.aula = Aula.objects.create(professor_diario=d.professor_diario, data=datetime.date(2013, 2, 1), conteudo='Conteúdo da Aula Teste', quantidade=2)

    d.material_aula = MaterialAula.objects.create(professor=d.professor, descricao='Material Teste', url='http://example.com/material.pdf')

    d.material_diario = MaterialDiario.objects.create(
        material_aula=d.material_aula, professor_diario=d.professor_diario, data_vinculacao=datetime.date(2013, 2, 1)
    )

    d.trabalho = Trabalho.objects.create(
        diario=d.diario,
        titulo='Trabalho Teste',
        data_solicitacao=datetime.date(2013, 2, 1),
        data_limite_entrega=datetime.date(2013, 2, 10),
        etapa=1,
        descricao='Descrição do Trabalho Teste',
    )

    d.topico = TopicoDiscussao.objects.create(
        diario=d.diario,
        etapa=1,
        user=d.user,
        titulo='Tópico Teste',
        descricao='Descrição do Tópico Teste',
    )

    d.mensagem = MensagemEntrada.objects.create(
        remetente=d.user,
        assunto='Assunto da mensagem',
        conteudo='Conteúdo da mensagem',
    )
    d.mensagem.destinatarios.add(d.user_aluno)

    return d


class TestEnsino:
    def test_get_periodos(self, api_client, dados_ensino):
        response = api_client.get('/api/ensino/periodos/', user=dados_ensino.user_aluno, application='token')

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['semestre'] == f'{dados_ensino.ano_2013.ano}.1'

    def test_get_diarios(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/diarios/{dados_ensino.ano_2013.ano}.1/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['id'] == dados_ensino.diario.id
        assert data[0]['disciplina']['descricao'] == dados_ensino.componente.descricao

    def test_get_diario_professores(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/diarios/{dados_ensino.diario.id}/professores/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['matricula'] == dados_ensino.professor.get_matricula()
        assert data[0]['nome'] == dados_ensino.professor.get_nome()

    def test_get_diario_alunos(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/diarios/{dados_ensino.diario.id}/alunos/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['matricula'] == dados_ensino.aluno.matricula
        assert data[0]['nome'] == dados_ensino.aluno.pessoa_fisica.nome

    def test_get_diario_aulas(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/diarios/{dados_ensino.diario.id}/aulas/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['conteudo'] == dados_ensino.aula.conteudo
        assert data[0]['qtd_aulas'] == dados_ensino.aula.quantidade

    def test_get_diario_materiais(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/diarios/{dados_ensino.diario.id}/materiais/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['descricao'] == dados_ensino.material_aula.descricao
        assert data[0]['url'] == dados_ensino.material_aula.url

    def test_get_diario_material(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/materiais/{dados_ensino.material_diario.id}/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()
        assert data['descricao'] == dados_ensino.material_aula.descricao
        assert data['url'] == dados_ensino.material_aula.url

    def test_get_diario_trabalhos(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/diarios/{dados_ensino.diario.id}/trabalhos/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['titulo'] == dados_ensino.trabalho.titulo
        assert data[0]['descricao'] == dados_ensino.trabalho.descricao

    def test_get_diario_trabalho(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/trabalhos/{dados_ensino.trabalho.id}/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()
        assert data['titulo'] == dados_ensino.trabalho.titulo
        assert data['descricao'] == dados_ensino.trabalho.descricao

    def test_get_diario_topicos(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/diarios/{dados_ensino.diario.id}/topicos/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['titulo'] == dados_ensino.topico.titulo
        assert data[0]['descricao'] == dados_ensino.topico.descricao

    def test_get_disciplinas(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/disciplinas/{dados_ensino.ano_2013.ano}.1/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['id'] == dados_ensino.matricula_diario.id
        assert data[0]['descricao'] == dados_ensino.componente.descricao
        assert data[0]['sigla'] == dados_ensino.componente.sigla

    def test_get_disciplinas_etapas(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/disciplinas/{dados_ensino.matricula_diario.id}/etapas/', user=dados_ensino.user_aluno)

        assert response.status_code == 200
        data = response.json()
        assert data['count'] == 3
        etapas = [r['numero_etapa'] for r in data['results']]
        assert 1 in etapas
        assert 2 in etapas
        assert 5 in etapas

    def test_get_mensagem_entrada_status(self, api_client, dados_ensino):
        response = api_client.get('/api/ensino/mensagens/entrada/nao-lidas/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['id'] == dados_ensino.mensagem.id
        assert data[0]['assunto'] == dados_ensino.mensagem.assunto
        assert data[0]['registro_leitura'] is False

    def test_post_registro_leitura(self, api_client, dados_ensino):
        response = api_client.post(f'/api/ensino/mensagens/registro-leitura/{dados_ensino.mensagem.id}/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        assert response.json() is True
        assert RegistroLeitura.objects.filter(mensagem=dados_ensino.mensagem, destinatario=dados_ensino.user_aluno).exists()

    def test_get_diario_material_pdf(self, api_client, dados_ensino):
        response = api_client.get(
            f'/api/ensino/materiais/{dados_ensino.diario.id}/{dados_ensino.material_aula.id}/pdf/',
            user=dados_ensino.user_aluno,
            HTTP_HOST='testserver',
        )
        assert response.status_code == 200
        assert response.json() == f'http://testserver{dados_ensino.material_aula.get_absolute_url()}'

    def test_post_registro_exclusao(self, api_client, dados_ensino):
        response = api_client.delete(f'/api/ensino/mensagens/registro-exclusao/{dados_ensino.mensagem.id}/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        assert response.json() is True

    def test_get_meus_dados_aluno(self, api_client, dados_ensino):
        with (
            mock.patch('edu.models.Aluno.get_ira', return_value=8.5),
            mock.patch('edu.models.Aluno.get_situacao_sistemica', return_value=('Ativo', 'Ativo')),
            mock.patch('rh.models.PessoaFisica.tem_digital', return_value=True),
            mock.patch('edu.models.Aluno.periodo_atual', new_callable=mock.PropertyMock, return_value=1),
        ):
            response = api_client.get('/api/ensino/meus-dados-aluno/', user=dados_ensino.user_aluno)
            assert response.status_code == 200
            data = response.json()
            assert data['curso'] == str(dados_ensino.aluno.curso_campus)

    def test_get_requisitos_conclusao(self, api_client, dados_ensino):
        response = api_client.get('/api/ensino/requisitos-conclusao/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        data = response.json()
        assert 'totais' in data
        assert 'ch_esperada' in data['totais']

    def test_obtem_meu_boletim(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/meu-boletim/{dados_ensino.ano_2013.ano}/{1}/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['codigo_diario'] == str(dados_ensino.matricula_diario.diario.id)

    def test_turma_virtual(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/minha-turma-virtual/{dados_ensino.diario.id}/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        data = response.json()
        # MatriculaDiarioSchema.id expõe o id do DIÁRIO (alias 'diario.id'), não do MatriculaDiario.
        # A asserção antiga comparava com matricula_diario.id (ids de tabelas distintas) e só passava
        # por coincidência do estado de sequência sob --reuse-db — daí a fragilidade.
        assert data['id'] == dados_ensino.diario.id

    def test_obtem_turmas_virtuais(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/minhas-turmas-virtuais/{dados_ensino.ano_2013.ano}/{1}/', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['id'] == str(dados_ensino.matricula_diario.diario.id)

    def test_obtem_token_acesso_responsaveis(self, api_client, dados_ensino):
        chave = dados_ensino.aluno.get_chave_responsavel()
        response = api_client.post(f'/api/ensino/autenticacao/acesso-responsaveis/?matricula={dados_ensino.aluno.matricula}&chave={chave}')
        assert response.status_code == 200
        assert 'token' in response.json()

    def test_obtem_meus_diarios(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/meus-diarios/{dados_ensino.ano_2013.ano}/{1}/', user=dados_ensino.user_professor)
        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data == [
            {
                'id': dados_ensino.diario.id,
                'ano_letivo': 2013,
                'periodo_letivo': 1,
                'componente_curricular': 'MAT - Matemática - Graduação [60 h/80 Aulas] ',
                'professores': [
                    {
                        'foto': 'http://localhost:8000/static/comum/img/default.jpg',
                        'nome': dados_ensino.servidor.pessoa_fisica.nome,
                        'nome_usual': dados_ensino.servidor.pessoa_fisica.nome,
                        'matricula': dados_ensino.servidor.matricula,
                        'email': 'professor.admin@ifrn.edu.br',
                    }
                ],
                'locais_de_aula': [],
                'data_inicio': '2013-01-01',
                'data_fim': '2013-06-30',
                'participantes': [
                    {
                        'foto': 'http://localhost:8000/static/comum/img/default.jpg',
                        'nome': 'Aluno Teste',
                        'nome_social': '',
                        'matricula': '20201010101',
                        'email': '',
                    }
                ],
                'aulas': [
                    {
                        'data': '2013-02-01',
                        'etapa': 1,
                        'quantidade': 2,
                        'professor': dados_ensino.servidor.pessoa_fisica.nome,
                        'conteudo': 'Conteúdo da Aula Teste',
                    }
                ],
                'materiais_de_aula': [{'url': 'http://example.com/material.pdf', 'descricao': 'Material Teste', 'data_vinculacao': '2013-02-01'}],
                'horarios': [],
            }
        ]

    def test_meus_diarios_ead(self, api_client, dados_ensino):
        esperado = [{'nome': f'{dados_ensino.diario.id} - MAT - Matemática', 'ano': 2013, 'periodo': 1, 'identificador': dados_ensino.diario.id}]

        # Como aluno
        response = api_client.get('/api/ensino/meus-diarios-ead/', user=dados_ensino.user_aluno, HTTP_AUTHORIZATION='Bearer token')
        assert response.status_code == 200
        assert response.json()['results'] == esperado

        # Como professor
        response = api_client.get('/api/ensino/meus-diarios-ead/', user=dados_ensino.user_professor, HTTP_AUTHORIZATION='Bearer token')
        assert response.status_code == 200
        assert response.json()['results'] == esperado

    def test_obtem_dados_aluno(self, api_client, dados_ensino):
        response = api_client.get(f'/api/ensino/aluno-resumido/?matricula={dados_ensino.aluno.matricula}', user=dados_ensino.user_professor)
        assert response.status_code == 200
        data = response.json()
        # aluno-resumido retorna list[DadosSiabiSchema]
        assert len(data) == 1
        assert data[0]['aluno']['matricula'] == dados_ensino.aluno.matricula

    def test_portal_professores(self, api_client, dados_ensino) -> None:
        ConfiguracaoDadosDocentes.objects.create(
            professor=dados_ensino.professor,
            modo_exibicao=ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA,
        )

        with mock.patch('edu.models.Professor.servidores_docentes.filter', return_value=Professor.objects.all()):
            response = api_client.get('/api/ensino/portal-professores/', user=dados_ensino.user_professor)
            assert response.status_code == 200
            data = response.json()['results']
            assert data[0]['nome'] == dados_ensino.professor.get_nome()
            assert data[0]['modo_exibicao'] == ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA

    def test_portal_professores_sem_materiais_visiveis_retorna_lista_vazia(self, api_client, dados_ensino) -> None:
        ConfiguracaoDadosDocentes.objects.create(
            professor=dados_ensino.professor,
            modo_exibicao=ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA,
        )
        # dados_ensino.material_aula existe mas fica com exibir_no_portal=False (default).

        with mock.patch('edu.models.Professor.servidores_docentes.filter', return_value=Professor.objects.all()):
            response = api_client.get('/api/ensino/portal-professores/', user=dados_ensino.user_professor)

        assert response.status_code == 200
        assert response.json()['results'][0]['materiais_aula'] == []

    def test_portal_professores_multiplos_materiais_na_mesma_disciplina_ordenados_por_data(self, api_client, dados_ensino) -> None:
        ConfiguracaoDadosDocentes.objects.create(
            professor=dados_ensino.professor,
            modo_exibicao=ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA,
        )
        dados_ensino.material_aula.exibir_no_portal = True
        dados_ensino.material_aula.save()

        material_mais_novo = MaterialAula.objects.create(
            professor=dados_ensino.professor, descricao='Slides Mais Novos', url='http://example.com/slides.pdf', exibir_no_portal=True
        )
        MaterialDiario.objects.create(material_aula=material_mais_novo, professor_diario=dados_ensino.professor_diario)

        with mock.patch('edu.models.Professor.servidores_docentes.filter', return_value=Professor.objects.all()):
            response = api_client.get('/api/ensino/portal-professores/', user=dados_ensino.user_professor)

        assert response.status_code == 200
        materiais_por_disciplina = response.json()['results'][0]['materiais_aula']
        assert len(materiais_por_disciplina) == 1

        grupo = materiais_por_disciplina[0]
        assert len(grupo['materiais']) == 2
        # Mais recente (por data_cadastro) primeiro.
        assert grupo['materiais'][0]['descricao'] == material_mais_novo.descricao
        assert grupo['materiais'][1]['descricao'] == dados_ensino.material_aula.descricao

    def test_portal_professores_material_em_diarios_de_disciplinas_diferentes_aparece_nos_dois_grupos(self, api_client, dados_ensino) -> None:
        ConfiguracaoDadosDocentes.objects.create(
            professor=dados_ensino.professor,
            modo_exibicao=ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA,
        )
        dados_ensino.material_aula.exibir_no_portal = True
        dados_ensino.material_aula.save()

        segundo_componente = Componente.objects.create(
            descricao='Português',
            sigla='POR',
            tipo=dados_ensino.tipo_componente,
            diretoria=dados_ensino.diretoria,
            nivel_ensino=dados_ensino.nivel_ensino,
            ch_hora_relogio=60,
            ch_hora_aula=80,
            ch_qtd_creditos=4,
        )
        segunda_componente_curricular = ComponenteCurricular.objects.create(
            matriz=dados_ensino.matriz,
            componente=segundo_componente,
            periodo_letivo=1,
            tipo=ComponenteCurricular.TIPO_REGULAR,
            qtd_avaliacoes=2,
            nucleo=dados_ensino.nucleo,
            ch_presencial=60,
            ch_pratica=0,
            optativo=False,
        )
        d2 = copy.copy(dados_ensino)
        d2.componente_curricular = segunda_componente_curricular
        segundo_diario = _inserir_diario_via_sql(d2)
        segundo_professor_diario = ProfessorDiario.objects.create(
            professor=dados_ensino.professor, diario=segundo_diario, tipo=dados_ensino.tipo_professor_diario, ativo=True
        )
        MaterialDiario.objects.create(material_aula=dados_ensino.material_aula, professor_diario=segundo_professor_diario)

        with mock.patch('edu.models.Professor.servidores_docentes.filter', return_value=Professor.objects.all()):
            response = api_client.get('/api/ensino/portal-professores/', user=dados_ensino.user_professor)

        assert response.status_code == 200
        materiais_por_disciplina = response.json()['results'][0]['materiais_aula']
        assert len(materiais_por_disciplina) == 2

        siglas = {grupo['sigla'] for grupo in materiais_por_disciplina}
        assert siglas == {dados_ensino.componente.sigla, segundo_componente.sigla}
        for grupo in materiais_por_disciplina:
            assert grupo['materiais'][0]['descricao'] == dados_ensino.material_aula.descricao

        # Ordenados por sigla do componente: 'MAT' (Matemática) vem antes de 'POR' (Português).
        assert materiais_por_disciplina[0]['sigla'] == dados_ensino.componente.sigla
        assert materiais_por_disciplina[1]['sigla'] == segundo_componente.sigla

    def test_portal_professores_agrupa_materiais_por_disciplina(self, api_client, dados_ensino) -> None:
        ConfiguracaoDadosDocentes.objects.create(
            professor=dados_ensino.professor,
            modo_exibicao=ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA,
        )
        dados_ensino.material_aula.exibir_no_portal = True
        dados_ensino.material_aula.save()

        with mock.patch('edu.models.Professor.servidores_docentes.filter', return_value=Professor.objects.all()):
            response = api_client.get('/api/ensino/portal-professores/', user=dados_ensino.user_professor)

        assert response.status_code == 200
        materiais_por_disciplina = response.json()['results'][0]['materiais_aula']
        assert len(materiais_por_disciplina) == 1

        grupo = materiais_por_disciplina[0]
        assert grupo['disciplina'] == dados_ensino.componente.descricao
        assert grupo['sigla'] == dados_ensino.componente.sigla
        assert len(grupo['materiais']) == 1
        assert grupo['materiais'][0]['descricao'] == dados_ensino.material_aula.descricao

    def test_portal_professores_material_sem_diario_fica_agrupado_a_parte(self, api_client, dados_ensino) -> None:
        ConfiguracaoDadosDocentes.objects.create(
            professor=dados_ensino.professor,
            modo_exibicao=ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA,
        )
        material_sem_diario = MaterialAula.objects.create(
            professor=dados_ensino.professor, descricao='Material Órfão', url='http://example.com/orfao.pdf', exibir_no_portal=True
        )

        with mock.patch('edu.models.Professor.servidores_docentes.filter', return_value=Professor.objects.all()):
            response = api_client.get('/api/ensino/portal-professores/', user=dados_ensino.user_professor)

        assert response.status_code == 200
        materiais_por_disciplina = response.json()['results'][0]['materiais_aula']
        assert len(materiais_por_disciplina) == 1

        grupo = materiais_por_disciplina[0]
        assert grupo['disciplina'] is None
        assert grupo['sigla'] is None
        assert len(grupo['materiais']) == 1
        assert grupo['materiais'][0]['descricao'] == material_sem_diario.descricao

    def test_portal_professores_material_sem_arquivo_retorna_url_vazia(self, api_client, dados_ensino) -> None:
        ConfiguracaoDadosDocentes.objects.create(
            professor=dados_ensino.professor,
            modo_exibicao=ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA,
        )
        # `arquivo` nunca foi anexado (só `url` externa) -> get_url_portal() retorna None.
        dados_ensino.material_aula.exibir_no_portal = True
        dados_ensino.material_aula.save()

        with mock.patch('edu.models.Professor.servidores_docentes.filter', return_value=Professor.objects.all()):
            response = api_client.get('/api/ensino/portal-professores/', user=dados_ensino.user_professor)

        assert response.status_code == 200
        grupo = response.json()['results'][0]['materiais_aula'][0]
        assert grupo['materiais'][0]['url'] == ''

    def test_schema_portal_professores_lista_modo_exibicao(self) -> None:
        from suap.api import api

        schema = api.get_openapi_schema()
        resposta = schema['paths']['/api/ensino/portal-professores/']['get']['responses'][200]

        assert resposta['content']['application/json']['schema']['$ref'] == '#/components/schemas/PagedDadosProfessorPortalInstitucionalSchema'
        assert 'modo_exibicao' in schema['components']['schemas']['DadosProfessorPortalInstitucionalSchema']['properties']

    def test_aluno_matriculado(self, api_client, dados_ensino):
        # Como aluno
        response = api_client.get(f'/api/ensino/aluno-matriculado/?matricula={dados_ensino.aluno.matricula}', user=dados_ensino.user_aluno)
        assert response.status_code == 200
        assert response.json()['matricula'] == dados_ensino.aluno.matricula

        # Como professor (não é aluno -> cai no get_object_or_404, deve funcionar)
        response = api_client.get(f'/api/ensino/aluno-matriculado/?matricula={dados_ensino.aluno.matricula}', user=dados_ensino.user_professor)
        assert response.status_code == 200
        assert response.json()['matricula'] == dados_ensino.aluno.matricula


def test_obtem_meus_periodos_letivos(api_client, fake_user):
    # Passthrough sem banco: o endpoint só valida o aluno (descarta o retorno) e serializa
    # dicts puros vindos de get_periodos. Mockamos get_aluno e get_instance -> nenhuma query.
    periodo_instance = mock.Mock()
    periodo_instance.get_periodos.return_value = [(2013, 1)]
    with (
        mock.patch('api.endpoints.ensino.get_aluno'),
        mock.patch('edu.models.PeriodoLetivoAtual.get_instance', return_value=periodo_instance),
    ):
        response = api_client.get('/api/ensino/meus-periodos-letivos/', user=fake_user)
        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 1
        assert data[0]['ano_letivo'] == 2013
        assert data[0]['periodo_letivo'] == 1


@pytest.mark.django_db
def test_obtem_minhas_avaliacoes(api_client, fake_user):
    # Cria exatamente as 5 avaliações esperadas (objetos reais p/ a serialização) e mocka
    # get_aluno + get_avaliacoes -> não precisa de servidor nem campus, só do schema.
    # Determinístico: lista ordenada explícita, nunca ItemConfiguracaoAvaliacao.objects.all()
    # (que vazaria itens de outros testes via fixture commitada e ordem de heap arbitrária).
    config = ConfiguracaoAvaliacao.objects.create(forma_calculo=ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ARITMETICA, etapa='1')
    avaliacoes = [
        ItemConfiguracaoAvaliacao.objects.create(
            configuracao_avaliacao=config,
            tipo=ItemConfiguracaoAvaliacao.TIPO_PROVA,
            sigla=f'A{i}',
            peso=10,
            nota_maxima=100,
        )
        for i in range(1, 6)
    ]
    aluno = mock.Mock()
    aluno.get_avaliacoes.return_value = avaliacoes
    with mock.patch('api.endpoints.ensino.get_aluno', return_value=aluno):
        response = api_client.get('/api/ensino/minhas-proximas-avaliacoes/', user=fake_user)

        assert response.status_code == 200
        data = response.json()['results']
        assert len(data) == 5
        assert data[0]['sigla'] == 'A1'
        assert data[4]['sigla'] == 'A5'
