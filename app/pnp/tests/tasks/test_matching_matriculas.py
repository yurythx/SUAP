import pytest

from comum.models import Ano
from edu.models import Aluno, CursoCampus, Diretoria, Modalidade
from edu.tests.factories import SituacaoMatriculaFactory
from pnp.matching import IndiceDeAlunos, get_cpf, normalizar_curso, resolver_aluno
from pnp.models import EstruturaPNP
from rh.deduplicacao.entrada import Politica
from rh.models import PessoaFisica, Setor, TipoUnidadeOrganizacional, UnidadeOrganizacional

CODIGO_ESTRUTURA = '26435.2409407.01.001'


def criar_uo(nome: str, sigla: str) -> UnidadeOrganizacional:
    tipo, _ = TipoUnidadeOrganizacional.objects.get_or_create(
        id=UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO, defaults={'descricao': 'Campus Produtivo'}
    )
    setor = Setor.objects.create(nome=nome, sigla=sigla)
    return UnidadeOrganizacional.objects.create(nome=nome, sigla=sigla, setor=setor, tipo=tipo)


def criar_curso(uo: UnidadeOrganizacional, descricao: str, historico: str = '') -> CursoCampus:
    diretoria, _ = Diretoria.objects.get_or_create(setor=uo.setor)
    modalidade, _ = Modalidade.objects.get_or_create(descricao='Integrado')
    return CursoCampus.objects.create(
        descricao=descricao,
        descricao_historico=historico or descricao,
        diretoria=diretoria,
        modalidade=modalidade,
        codigo=f'{uo.sigla}-{CursoCampus.objects.count()}',
    )


def criar_aluno(nome: str, cpf: str, matricula: str, curso: CursoCampus) -> Aluno:
    pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'nome': nome, 'cpf': cpf}, Politica.PREENCHER)
    ano, _ = Ano.objects.get_or_create(ano=2024)
    situacao = SituacaoMatriculaFactory()
    return Aluno.objects.create(
        matricula=matricula, pessoa_fisica=pessoa_fisica, curso_campus=curso, ano_letivo=ano, periodo_letivo=1, situacao=situacao
    )


def linha(**kwargs) -> dict:
    padrao = {
        'matricula': '123231971',
        'cpf': '71122551479',
        'nome': 'AALIYAH HADASSAH RONNIE AQUINO LEITE',
        'curso': 'TÉCNICO EM ALIMENTOS',
        'unidade': 'Campus Pau dos Ferros',
        'codigo_estrutura': CODIGO_ESTRUTURA,
    }
    return {**padrao, **kwargs}


@pytest.fixture
def campus(db):
    uo = criar_uo('CAMPUS PAU DOS FERROS', 'PF')
    EstruturaPNP.objects.create(codigo=CODIGO_ESTRUTURA, nome='Campus Pau dos Ferros', uo=uo)
    return uo


def test_get_cpf_descarta_o_sentinela_da_pnp():
    assert get_cpf('71122551479') == '71122551479'
    assert get_cpf('711.225.514-79') == '71122551479'
    assert get_cpf('-0000000000') == ''
    assert get_cpf('00000000000') == ''


def test_normalizar_curso_remove_o_prefixo_fic_e_o_programa():
    assert normalizar_curso('FIC+ Agente Cultural [PRONATEC]') == normalizar_curso('AGENTE CULTURAL')
    assert normalizar_curso('FIC - PORTUGUÊS BÁSICO') == normalizar_curso('Português Básico')


@pytest.mark.django_db
def test_cpf_unico_vincula_sem_precisar_do_curso(campus):
    curso = criar_curso(campus, 'Técnico em Alimentos')
    aluno = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', curso)

    assert resolver_aluno(linha(curso='CURSO QUE NAO EXISTE'), IndiceDeAlunos()) == aluno.id


@pytest.mark.django_db
def test_cpf_com_varios_cursos_e_desempatado_pelo_nome_do_curso(campus):
    alimentos = criar_curso(campus, 'Técnico em Alimentos')
    informatica = criar_curso(campus, 'Técnico em Informática')
    aluno_alimentos = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', alimentos)
    criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040002', informatica)

    assert resolver_aluno(linha(curso='TÉCNICO EM ALIMENTOS'), IndiceDeAlunos()) == aluno_alimentos.id


@pytest.mark.django_db
def test_curso_com_nome_apenas_parecido_ainda_desempata(campus):
    """O SUAP grafa o curso com o adorno do programa; a PNP exporta o nome cru."""
    fic = criar_curso(campus, 'FIC+ Operador de Computadores [PRONATEC]', historico='Operador de Computadores')
    informatica = criar_curso(campus, 'Técnico em Informática')
    aluno_fic = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', fic)
    criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040002', informatica)

    assert resolver_aluno(linha(curso='OPERADOR DE COMPUTADORES'), IndiceDeAlunos()) == aluno_fic.id


@pytest.mark.django_db
def test_cpf_com_varios_cursos_e_desempatado_pela_unidade(campus):
    outro_campus = criar_uo('CAMPUS MOSSORÓ', 'MO')
    daqui = criar_curso(campus, 'Técnico em Alimentos')
    de_fora = criar_curso(outro_campus, 'Técnico em Alimentos')
    aluno_daqui = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', daqui)
    criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040002', de_fora)

    assert resolver_aluno(linha(), IndiceDeAlunos()) == aluno_daqui.id


@pytest.mark.django_db
def test_curso_ambiguo_nao_vincula(campus):
    """Dois cursos de mesmo nome na mesma unidade: sem critério para escolher, não escolhe."""
    primeiro = criar_curso(campus, 'Técnico em Alimentos')
    segundo = criar_curso(campus, 'Técnico em Alimentos', historico='Técnico em Alimentos (noturno)')
    criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', primeiro)
    criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040002', segundo)

    assert resolver_aluno(linha(), IndiceDeAlunos()) is None


@pytest.mark.django_db
def test_cpf_desconhecido_recorre_ao_nome_dentro_do_curso(campus):
    curso = criar_curso(campus, 'Técnico em Alimentos')
    aluno = criar_aluno('AALIYAH HADASSAH RONNIE AQUINO LEITE', '735.735.735-09', '20211014040001', curso)

    assert resolver_aluno(linha(cpf='-0000000000'), IndiceDeAlunos()) == aluno.id


@pytest.mark.django_db
def test_nome_malformado_da_origem_nao_e_usado_na_busca(campus):
    curso = criar_curso(campus, 'Técnico em Alimentos')
    criar_aluno('AALIYAH HADASSAH RONNIE AQUINO LEITE', '735.735.735-09', '20211014040001', curso)

    malformado = '10\t202521510360045\tAALIYAH HADASSAH RONNIE AQUINO LEITE\t12/10/2001\tOUTRA PESSOA'
    assert resolver_aluno(linha(cpf='-0000000000', nome=malformado), IndiceDeAlunos()) is None


@pytest.mark.django_db
def test_aluno_ja_vinculado_a_outra_matricula_nao_e_reaproveitado(campus):
    from pnp.models import MatriculaPNP

    curso = criar_curso(campus, 'Técnico em Alimentos')
    aluno = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', curso)
    MatriculaPNP.objects.create(matricula='outra', nome='OUTRO REGISTRO', aluno=aluno)

    assert resolver_aluno(linha(), IndiceDeAlunos()) is None


@pytest.mark.django_db
def test_estrutura_nao_importada_nao_impede_o_vinculo_pelo_cpf():
    uo = criar_uo('CAMPUS PAU DOS FERROS', 'PF')
    curso = criar_curso(uo, 'Técnico em Alimentos')
    aluno = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', curso)

    assert resolver_aluno(linha(), IndiceDeAlunos()) == aluno.id
