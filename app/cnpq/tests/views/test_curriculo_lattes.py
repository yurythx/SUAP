from types import SimpleNamespace

from django.conf import settings

import pytest

from cnpq.utils import extrair_dados_curriculo_lattes
from cnpq.xml_parsers import CurriculoVittaeLattesParser
from comum.types import PessoaFisicaCadastro, ServidorCadastro
from rh.models import CargoEmprego, JornadaTrabalho, Servidor, Setor, Situacao


class QuerySetFake(list):
    def all(self):
        return self

    def order_by(self, *args):
        return self


def _lista_vazia():
    return QuerySetFake()


def test_extrair_dados_curriculo_lattes_decodifica_entidades_html():
    formacao = SimpleNamespace(
        get_tipo=lambda: 'Mestrado',
        nome_curso='História &amp; Memória',
        nome_instituicao='Instituição',
        ano_inicio='2020',
        ano_conclusao='2022',
        titulo_trabalho_conclusao='&quot;Obreiros Pacíficos&quot;',
        nome_orientador='Orientador',
    )
    premio = SimpleNamespace(
        nome_premio_titulo='Trabalho &quot;Destaque&quot;',
        nome_entidade_promotora='Evento &amp; Mostra',
        ano_premiacao='2024',
    )
    dado_geral = SimpleNamespace(
        texto_resumo='Linha 1&#10;Linha 2 com &quot;aspas&quot;',
        formacoes_academicas_titulacoes=QuerySetFake([formacao]),
        areas_atuacoes=_lista_vazia(),
    )
    curriculo = SimpleNamespace(
        dado_geral=dado_geral,
        numero_identificador='123',
        grupos_pesquisa=_lista_vazia(),
        get_premios_e_titulos=lambda: [premio],
        get_artigos_completos=_lista_vazia,
        get_artigos_resumos=_lista_vazia,
        get_trabalhos_eventos=_lista_vazia,
        get_livros=_lista_vazia,
        get_capitulos=_lista_vazia,
        get_textos_jornal_revista=_lista_vazia,
        get_prefacios_posfacios=_lista_vazia,
        get_traducoes=_lista_vazia,
        get_outras_producoes=_lista_vazia,
        get_softwares=_lista_vazia,
        get_produtos_tecnologicos=_lista_vazia,
        get_processos_tecnicas=_lista_vazia,
        get_trabalhos_tecnicos=_lista_vazia,
        get_patentes=_lista_vazia,
        get_projeto_pesquisa=_lista_vazia,
        get_projeto_extensao=_lista_vazia,
        get_projeto_desenvolvimento=_lista_vazia,
    )

    dados = extrair_dados_curriculo_lattes(curriculo)

    assert dados['biografia'] == 'Linha 1\nLinha 2 com "aspas"'
    assert dados['formacao_academica'][0]['curso'] == 'História & Memória'
    assert dados['formacao_academica'][0]['titulo'] == '"Obreiros Pacíficos"'
    assert dados['premios_titulos'][0]['nome'] == 'Trabalho "Destaque"'
    assert dados['premios_titulos'][0]['entidade'] == 'Evento & Mostra'


class TestCurriculoLattes:
    @pytest.fixture(autouse=True)
    def _setup(self, client, substrato_cnpq):
        self.client = client
        self.client.login(username=substrato_cnpq.get_user().username, password='123')
        self.servidor_cnpq = self._criar_servidor_cnpq()

    def _criar_servidor_cnpq(self):
        setor_a1_suap = Setor.objects.get(sigla='A1', nome='A1', codigo=None)
        setor_a1_siape = Setor.objects.get(sigla='A1', nome='A1', codigo='A1')
        situacao = Situacao.objects.get(codigo=Situacao.ATIVO_PERMANENTE)
        jornada = JornadaTrabalho.objects.get_or_create(codigo='01', nome='40h', excluido=False)[0]
        cargo = CargoEmprego.objects.get(codigo='01')

        pessoa_fisica_dict: PessoaFisicaCadastro = {
            'nome_registro': 'Servidor 1',
            'template': b'1',
            'email': 'servidor.aleatorio@mail.gov',
            'cpf': '707.651.200-97',
        }
        dados: ServidorCadastro = {
            'matricula': '12121212',
            'pessoa_fisica': pessoa_fisica_dict,
            'ativo': True,
            'situacao': situacao,
            'cargo_emprego': cargo,
            'setor': setor_a1_suap,
            'setor_lotacao': setor_a1_siape,
            'setor_exercicio': setor_a1_siape,
            'jornada_trabalho': jornada,
        }
        retorno = Servidor.update_or_create(dados)
        return retorno['servidor']

    def _importar_curriculo_xml(self):
        arquivo = f'{settings.BASE_DIR}/cnpq/tests_files/curriculo.xml'
        with open(arquivo, encoding='latin-1') as file:
            curriculo_str = file.read()
        parser = CurriculoVittaeLattesParser(curriculo_str, '', '')
        assert parser.parse(self.servidor_cnpq.get_vinculo())

    def _importar_curriculo_xml_minimo(self, orcid):
        curriculo_str = f'''
        <CURRICULO-VITAE SISTEMA-ORIGEM-XML="LATTES_OFFLINE" DATA-ATUALIZACAO="04022015" HORA-ATUALIZACAO="223241" NUMERO-IDENTIFICADOR="5173495516982528">
            <DADOS-GERAIS NOME-COMPLETO="Servidor CNPq" NOME-EM-CITACOES-BIBLIOGRAFICAS="" NACIONALIDADE="B" CPF="" NUMERO-DO-PASSAPORTE=""
                PAIS-DE-NASCIMENTO="Brasil" UF-NASCIMENTO="RN" CIDADE-NASCIMENTO="Natal" DATA-NASCIMENTO="" SEXO="" NUMERO-IDENTIDADE=""
                ORGAO-EMISSOR="" UF-ORGAO-EMISSOR="" DATA-DE-EMISSAO="" NOME-DO-PAI="" NOME-DA-MAE="" PERMISSAO-DE-DIVULGACAO="NAO"
                NOME-DO-ARQUIVO-DE-FOTO="" TEXTO-RESUMO-CV-RH="" OUTRAS-INFORMACOES-RELEVANTES="" ORCID-ID="{orcid}" />
        </CURRICULO-VITAE>
        '''
        parser = CurriculoVittaeLattesParser(curriculo_str, '', '')
        assert parser.parse(self.servidor_cnpq.get_vinculo())

    def test_visualizar_curriculo_exibe_texto_esperado(self):
        self._importar_curriculo_xml()

        resposta = self.client.get(f'/cnpq/curriculo/{self.servidor_cnpq.id}/')

        assert resposta.status_code == 200
        assert (
            'Professor de Sistemas de Informação do IFRN, Doutor em Engenharia Elétrica e da Computação pela UFRN, Tecnólogo em Desenvolvimento de Software pelo IFRN'
            in resposta.content.decode()
        )

    def test_importar_curriculo_preenche_orcid_quando_pessoa_nao_tem_orcid(self):
        self._importar_curriculo_xml_minimo('0000-0002-1825-0097')

        self.servidor_cnpq.pessoa_fisica.refresh_from_db()

        assert self.servidor_cnpq.pessoa_fisica.orcid == 'https://orcid.org/0000-0002-1825-0097'

    def test_importar_curriculo_mantem_orcid_informado_no_suap(self):
        self.servidor_cnpq.pessoa_fisica.orcid = 'https://orcid.org/0000-0001-1111-1111'
        self.servidor_cnpq.pessoa_fisica.save()

        self._importar_curriculo_xml_minimo('0000-0002-1825-0097')

        self.servidor_cnpq.pessoa_fisica.refresh_from_db()

        assert self.servidor_cnpq.pessoa_fisica.orcid == 'https://orcid.org/0000-0001-1111-1111'

    def test_importar_curriculo_ignora_orcid_maior_que_o_campo(self):
        self._importar_curriculo_xml_minimo('0' * 201)

        self.servidor_cnpq.pessoa_fisica.refresh_from_db()

        assert self.servidor_cnpq.pessoa_fisica.orcid == ''
