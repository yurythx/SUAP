import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group

from comum.models import Ano
from djtools.middleware import threadlocals as tl
from documento_eletronico.models import Documento, DocumentoTexto, ModeloDocumento, TipoDocumentoTexto
from documento_eletronico.status import DocumentoStatus
from edu.models import Aluno, CursoCampus, Diretoria
from edu.tests.factories import SituacaoMatriculaFactory
from rh.models import Servidor
from pesquisa.models import Edital as EditalPesquisa
from pesquisa.models import Projeto as ProjPesquisa
from projetos.models import Edital as EditalExtensao
from projetos.models import Participacao as PartExtensao
from projetos.models import Projeto as ProjExt


@pytest.fixture
def dados_institucional(servidor_a, campus_b) -> SimpleNamespace:

    grupo = Group.objects.create(name='Test Group')
    servidor_a.get_user().groups.add(grupo)

    ano_letivo = Ano.objects.create(ano=2021)
    tl.context.user = servidor_a.get_user()

    tipo_doc = TipoDocumentoTexto.objects.create(nome='Tipo Teste', consulta_publica=True)
    modelo_doc = ModeloDocumento.objects.create(nome='Modelo Teste', tipo_documento_texto=tipo_doc)
    DocumentoTexto.objects.create(
        assunto='Documento Público Teste',
        modelo=modelo_doc,
        status=DocumentoStatus.STATUS_FINALIZADO,
        setor_dono=servidor_a.setor,
        usuario_criacao=servidor_a.get_user(),
        corpo='Conteúdo de teste',
        data_ultima_modificacao=datetime.datetime.now(),
        usuario_ultima_modificacao=servidor_a.get_user(),
        nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
    )

    edital_pesquisa = EditalPesquisa.objects.create(
        titulo='Edital Pesquisa Teste',
        inicio_inscricoes=datetime.datetime.now() - datetime.timedelta(days=10),
        fim_inscricoes=datetime.datetime.now() + datetime.timedelta(days=10),
        tipo_edital=EditalPesquisa.PESQUISA,
    )
    projeto_pesquisa = ProjPesquisa(
        titulo='Projeto Pesquisa Teste',
        edital=edital_pesquisa,
        aprovado=True,
        pre_aprovado=True,
        uo=servidor_a.setor.uo,
        inicio_execucao=datetime.datetime.now().date(),
        fim_execucao=(datetime.datetime.now() + datetime.timedelta(days=30)).date(),
    )
    projeto_pesquisa.bolsa_coordenador = False
    projeto_pesquisa.save()

    edital_extensao = EditalExtensao.objects.create(
        titulo='Edital Extensao Teste',
        inicio_inscricoes=datetime.datetime.now() - datetime.timedelta(days=10),
        fim_inscricoes=datetime.datetime.now() + datetime.timedelta(days=10),
        tipo_edital=EditalExtensao.EXTENSAO,
        divulgacao_selecao=datetime.datetime.now() - datetime.timedelta(days=1),
    )
    projeto_extensao = ProjExt.objects.create(
        titulo='Projeto Extensao Teste',
        edital=edital_extensao,
        aprovado=True,
        pre_aprovado=True,
        uo=servidor_a.setor.uo,
        inicio_execucao=datetime.datetime.now().date(),
        fim_execucao=(datetime.datetime.now() + datetime.timedelta(days=30)).date(),
    )

    diretoria = Diretoria.objects.create(setor=servidor_a.setor)
    curso = CursoCampus.objects.create(
        codigo='APIINST',
        descricao='Curso Teste API Institucional',
        descricao_historico='Curso Teste API Institucional',
        diretoria=diretoria,
    )
    Aluno.objects.create(
        pessoa_fisica=servidor_a.pessoa_fisica,
        matricula='2021100000',
        situacao=SituacaoMatriculaFactory(),
        ano_letivo=ano_letivo,
        periodo_letivo=1,
        curso_campus=curso,
    )

    PartExtensao.objects.create(projeto=projeto_extensao, vinculo_pessoa=servidor_a.get_vinculo(), ativo=True, carga_horaria=20)

    return SimpleNamespace(servidor_a=servidor_a, campus_b=campus_b)


class TestInstitucional:
    def test_estatisticas(self, api_client, dados_institucional):
        # O endpoint expõe agregados GLOBAIS (`Aluno.ativos.count()`, `Servidor.objects.ativos()`,
        # contagens de projetos). Sob xdist (`pytest -n 4`) o banco do worker pode conter dados
        # ativos commitados por OUTROS testes (fixtures class-scoped sem teardown), então fixar
        # magnitudes absolutas torna o teste intermitente. Em vez disso, valida-se que o endpoint
        # reflete fielmente o estado atual do banco (espelho do ORM) e que agrupa/forma os dados
        # por campus corretamente para os registros conhecidos da fixture.
        response = api_client.get('/api/institucional/estatisticas/')
        assert response.status_code == 200
        data = response.json()['results']
        assert data['content_type'] == 'institucional.suap_em_numeros'
        assert data['id'] == 1

        # Escalares: o endpoint deve refletir exatamente as contagens do ORM no momento da request.
        assert data['alunos_ativos'] == Aluno.ativos.count()
        assert data['servidores_ativos'] == Servidor.objects.ativos().count()
        # Projetos: a fixture cria 1 de cada em execução; outros testes só podem aumentar.
        assert data['projetos_pesquisa_em_execucao'] >= 1
        assert data['projetos_extensao_em_execucao'] >= 1

        # Estrutura/agrupamento: os dados da fixture aparecem no campus correto.
        por_campus = {e['campus_id']: e for e in data['estatisticas_por_campus']}

        uo_a = dados_institucional.servidor_a.setor.uo
        assert uo_a.id in por_campus
        campus_a = por_campus[uo_a.id]
        assert campus_a['campus_sigla'] == uo_a.sigla
        assert campus_a['campus_nome'] == uo_a.nome
        assert campus_a['alunos_ativos'] >= 1
        assert campus_a['servidores_ativos'] >= 1

        uo_b = dados_institucional.campus_b
        assert uo_b.id in por_campus
        assert por_campus[uo_b.id]['campus_sigla'] == uo_b.sigla
        assert por_campus[uo_b.id]['servidores_ativos'] >= 1

    def test_documentos_publicos(self, api_client, dados_institucional):
        response = api_client.get('/api/institucional/consulta_publica/documentos/', user=dados_institucional.servidor_a.get_user())
        assert response.status_code == 200
        results = response.json()['results']
        assert len(results) == 1
        assert results[0]['assunto'] == 'Documento Público Teste'
