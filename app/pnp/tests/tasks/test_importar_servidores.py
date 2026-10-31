import pytest
from django.contrib.auth.models import Group

from pnp.models import EstruturaPNP, ServidorPNP
from pnp.tasks import importar_servidores, normalizar_matricula
from rh.models import PessoaFisica, Servidor, Situacao


# Servidor.save() sincroniza os papéis do usuário via comum.models, que faz Group.objects.get()
# de cada um destes nomes; em produção eles vêm do sync_permissions.
GRUPOS_EXIGIDOS_PELO_SYNC = [
    'Aluno',
    'Aposentado',
    'Auditor',
    'Auxiliar de Enfermagem',
    'Avaliador Externo',
    'Avaliador Interno',
    'Chefe de Setor',
    'Enfermeiro',
    'Fisioterapeuta',
    'Médico',
    'Nutricionista',
    'Odontólogo',
    'Professor',
    'Psicólogo',
    'Servidor',
    'Servidores Com Poder de Chefe',
    'Técnico em Enfermagem',
    'Técnico em Saúde Bucal',
    'Tramitador de processos',
    'Visualizador de Cursos e Concursos',
]


def criar_servidor(matricula: str, nome: str, cpf: str) -> Servidor:
    for grupo in GRUPOS_EXIGIDOS_PELO_SYNC:
        Group.objects.get_or_create(name=grupo)
    situacao, _ = Situacao.objects.get_or_create(
        codigo=Situacao.ATIVO_PERMANENTE, defaults={'nome': 'Ativo Permanente', 'nome_siape': 'ATIVO PERMANENTE'}
    )
    pessoa_fisica = PessoaFisica.objects.create(nome=nome, cpf=cpf)
    return Servidor.objects.create(matricula=matricula, pessoa_fisica=pessoa_fisica, situacao=situacao)


def linha(matricula: str, nome: str = 'FULANO DE TAL', cpf: str = '99540924715', codigo: str = '26435.2401008.01.001') -> list[str]:
    return [matricula, nome, cpf, 'Campus Apodi', codigo]


def test_normalizar_matricula_remove_zeros_a_esquerda_e_pontuacao():
    assert normalizar_matricula('0277346') == '277346'
    assert normalizar_matricula('1895370') == '1895370'
    assert normalizar_matricula('277.346') == '277346'


@pytest.mark.django_db
def test_importa_todas_as_linhas_vinculando_apenas_as_derivaveis():
    servidor = criar_servidor('277346', 'ADAO MARCELO', '734.734.734-30')
    estrutura = EstruturaPNP.objects.create(codigo='26435.2401008.01.001', nome='Campus Apodi')

    importar_servidores([linha('0277346', 'ADAO MARCELO DA ROCHA NETO'), linha('9999999', 'PESSOA INEXISTENTE')])

    vinculado = ServidorPNP.objects.get(matricula='277346')
    assert (vinculado.servidor, vinculado.estrutura) == (servidor, estrutura)
    assert (vinculado.nome, vinculado.unidade, vinculado.codigo_estrutura) == ('ADAO MARCELO DA ROCHA NETO', 'Campus Apodi', '26435.2401008.01.001')

    assert ServidorPNP.objects.get(matricula='9999999').servidor is None


@pytest.mark.django_db
def test_matriculas_equivalentes_geram_um_unico_registro():
    criar_servidor('277346', 'ADAO MARCELO', '734.734.734-30')

    importar_servidores([linha('0277346'), linha('277346')])

    assert ServidorPNP.objects.count() == 1


@pytest.mark.django_db
def test_servidor_ja_vinculado_a_outra_matricula_nao_e_roubado():
    servidor = criar_servidor('277346', 'ADAO MARCELO', '734.734.734-30')
    ServidorPNP.objects.create(matricula='999', nome='OUTRO REGISTRO', servidor=servidor)

    importar_servidores([linha('0277346')])

    assert ServidorPNP.objects.get(matricula='277346').servidor is None
    assert ServidorPNP.objects.get(matricula='999').servidor == servidor


@pytest.mark.django_db
def test_reimportacao_nao_duplica_nem_desfaz_vinculos():
    servidor = criar_servidor('277346', 'ADAO MARCELO', '734.734.734-30')
    estrutura = EstruturaPNP.objects.create(codigo='26435.2401008.01.001', nome='Campus Apodi')
    importar_servidores([linha('0277346')])

    importar_servidores([linha('0277346', 'ADAO MARCELO DA ROCHA NETO')])

    registro = ServidorPNP.objects.get()
    assert (registro.servidor, registro.estrutura, registro.nome) == (servidor, estrutura, 'ADAO MARCELO DA ROCHA NETO')


@pytest.mark.django_db
def test_estrutura_preenchida_manualmente_nao_e_apagada_quando_o_codigo_nao_existe():
    estrutura = EstruturaPNP.objects.create(codigo='outro-codigo', nome='Campus Apodi')
    importar_servidores([linha('9999999')])
    registro = ServidorPNP.objects.get()
    registro.estrutura = estrutura
    registro.save()

    importar_servidores([linha('9999999')])

    assert ServidorPNP.objects.get().estrutura == estrutura


@pytest.mark.django_db
def test_estrutura_e_vinculada_quando_passa_a_existir():
    importar_servidores([linha('9999999')])
    assert ServidorPNP.objects.get().estrutura is None

    estrutura = EstruturaPNP.objects.create(codigo='26435.2401008.01.001', nome='Campus Apodi')
    importar_servidores([linha('9999999')])

    assert ServidorPNP.objects.get().estrutura == estrutura
