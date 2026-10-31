import collections
import logging
from datetime import UTC, datetime

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from comum.models import PrestadorServico
from comum.pytest_fixtures import cadastrar_setor
import pytest
from documento_eletronico.models import Classificacao, Documento, DocumentoTexto, HipoteseLegal, NivelPermissao, TipoDocumentoTexto
from documento_eletronico.utils import get_setores_compartilhados
from processo_eletronico.models import ModeloDespacho, Processo, TipoProcesso
from rh.models import Atividade, CargoEmprego, Funcao, JornadaTrabalho, Papel, PessoaFisica, Servidor, ServidorFuncaoHistorico, Setor, Situacao
from rh.tests.factories import CargoEmpregoFactory, SituacaoFactory

logger = logging.getLogger(__name__)

GRUPO_GERENTE_SISTEMICO = 'Gerente Sistêmico de Documento Eletrônico'
GRUPO_OPERADOR_DOCUMENTO = 'Operador de Documento Eletrônico'
GRUPO_SERVIDOR = 'Servidor'

VISUALIZAR_COMO_PUBLICO = DocumentoTexto.NIVEL_ACESSO_PUBLICO
VISUALIZAR_COMO_RESTRITO = DocumentoTexto.NIVEL_ACESSO_RESTRITO
VISUALIZAR_COMO_SIGILOSO = DocumentoTexto.NIVEL_ACESSO_SIGILOSO


def assert_permissao_documento(documento_chave, usuario_chave, permissao, permitido, esperado):
    assert permitido == esperado, (
        f'Esperava que {usuario_chave} {"tivesse" if esperado else "não tivesse"} permissão para {permissao} '
        f'em {documento_chave}, mas o resultado foi {permitido}.'
    )


def print_dict(d, indent=0):
    for key, value in list(d.items()):
        logger.info('\t' * indent + str(key))
        if isinstance(value, dict):
            print_dict(value, indent + 1)
        else:
            logger.info('\t' * (indent + 1) + str(value))


def merge_nested_dict(d, u):
    for k, v in list(u.items()):
        if isinstance(v, collections.abc.Mapping):
            default = v.copy()
            default.clear()
            r = merge_nested_dict(d.get(k, default), v)
            d[k] = r
        else:
            d[k] = v
    return d


@pytest.mark.django_db(databases='__all__')
class TestPermissoesDocumentoEletronico:
    """
    Servidores self.servidor_a e self.servidor_a2 são do mesmo setor

    Exemplo de definições dos métodos:
        Método que edita um documento:
            _editar_documento
                Só faz a ação de editar, sem testar perfis nem usuários
            _test_editar_documento
                No fluxo normal de teste deve fazer todas as verificações, mas no início dele deve
                ter um que faça, se necessário a verificação da submissão pode diversos usuário.
                Exemplo: _test_editar_documento_pessoas que executaria
                a submissão em '/documento_eletronico/editar_documento/{:d}/', necessário isso porque
                se tiver mais que uma verificação e um usuário que não deveria pode executar a ação
                pode ser bloqueada na na primeira e poder ser executada a segunda
            _test_editar_documento_pessoas
                Testar a edição de documento para vários usuários passados como parâmetro


    """

    records = {}
    cadastrar_setor = staticmethod(cadastrar_setor)

    @pytest.fixture(autouse=True)
    def _montar_dados(self, db, sync_permissions):
        # Escopo de FUNÇÃO: era class-scoped e montava tudo dentro de
        # `django_db_blocker.unblock()`, ou seja, COMMITAVA a árvore de setores e os
        # servidores sem teardown. Custa um setup a mais porque a classe tem um teste só.
        cls = type(self)
        cls.records = {}
        cls.setUpTestData()

    @classmethod
    def setUpTestData(cls):
        cls._criar_tipos_e_modelos()
        cls._criar_setores()
        cls._criar_usuarios_e_permissoes()

    @classmethod
    def cadastrar(cls, modelo, data, chaves=None):
        if chaves is None:
            chaves = data
        qs = modelo.objects.filter(**chaves)
        if qs.exists():
            return qs[0]
        else:
            if modelo == Servidor:
                pessoa_dados = {}
                pessoa_dados['nome'] = data.pop('nome')
                pessoa_dados['template'] = data.pop('template', b'1')
                email = data.pop('email', '')  # email migrou de PessoaFisica p/ Vinculo.email_pessoal
                pessoa_dados['cpf'] = data.pop('cpf', '')
                pessoa_fisica = PessoaFisica.objects.create(**pessoa_dados)
                data['pessoa_fisica'] = pessoa_fisica
                objeto = modelo.objects.create(**data)
                vinculo = objeto.get_vinculo()
                if vinculo and email:
                    vinculo.email_pessoal = email
                    vinculo.save(update_fields=['email_pessoal'])
                user = objeto.get_user()
                user.set_password('123')
                user.save()
                objeto = modelo.objects.get(pk=objeto.pk)
            else:
                if modelo is PessoaFisica:
                    # email/foto/raca/... migraram p/ Vinculo; PessoaFisica avulsa (sem vínculo) não os armazena.
                    for _campo in (
                        'email',
                        'email_secundario',
                        'foto',
                        'raca',
                        'povo_indigena',
                        'deficiencia',
                        'sistema_origem',
                        'setores_adicionais',
                    ):
                        data.pop(_campo, None)
                objeto = modelo.objects.create(**data)
        return objeto

    @classmethod
    def _criar_tipos_e_modelos(cls):
        if not Classificacao.objects.exists():
            logger.info('Loading initial data for types and models')
            call_command('loaddata', '../fixtures/initial_data_01_classificacao.json', verbosity=0)
            call_command('loaddata', '../fixtures/initial_data_02_tipo_documento.json', verbosity=0)
            call_command('loaddata', '../fixtures/initial_data_03_modelo_documento.json', verbosity=0)

        logger.info('Classificacao carregada com sucesso')

    @classmethod
    def _criar_setores(cls):
        # atualizar_setor('RAIZ', 'IFRN')
        # Do `suap_data` este arquivo só usava o setor raiz; o resto da árvore ele mesmo
        # monta com `cadastrar_setor`, logo abaixo.
        #
        cls.records['setor_ifrn'], _ = Setor.objects.get_or_create(sigla='RAIZ', nome='RAIZ', codigo=None)
        cls.records['setor_ifrn_siap'] = cls.records['setor_ifrn']
        # IFRN -> RE
        cls.records['setor_re'], cls.records['setor_re_siap'] = cls.cadastrar_setor('RE', cls.records['setor_ifrn'], '00001')
        # IFRN -> RE -> DIGTI
        cls.records['setor_digti'], cls.records['setor_digti_siap'] = cls.cadastrar_setor('DIGTI', cls.records['setor_re'])
        # IFRN -> RE -> GABIN
        cls.records['setor_gabin'], cls.records['setor_gabin_siap'] = cls.cadastrar_setor('GABIN', cls.records['setor_re'])
        # IFRN -> RE -> PROPI
        cls.records['setor_propi'], cls.records['setor_propi_siap'] = cls.cadastrar_setor('PROPI', cls.records['setor_re'])
        # IFRN -> RE -> PROEX
        cls.records['setor_proex'], cls.records['setor_proex_siap'] = cls.cadastrar_setor('PROEX', cls.records['setor_re'])

        # IFRN -> RE -> DIGTI -> COSINF
        cls.records['setor_cosinf'], cls.records['setor_cosinf_siap'] = cls.cadastrar_setor('COSINF', cls.records['setor_digti'])
        # IFRN -> RE -> DIGTI -> COINRE
        cls.records['setor_coinre'], cls.records['setor_coinre_siap'] = cls.cadastrar_setor('COINRE', cls.records['setor_digti'])
        # IFRN -> RE -> DIGTI -> COSINF -> COSAAD
        cls.records['setor_cosaad'], cls.records['setor_cosaad_siap'] = cls.cadastrar_setor('COSAAD', cls.records['setor_cosinf'])
        # COSAAD é setor irmão da COSINF
        cls.records['setor_cosinf'].setores_compartilhados.add(cls.records['setor_cosaad'])
        cls.records['setor_cosinf'].save()
        # IFRN -> RE -> DG/CNAT
        cls.records['setor_dg_cnat'], cls.records['setor_dg_cnat_siape'] = cls.cadastrar_setor('DG/CNAT', cls.records['setor_re'], '00003')
        # IFRN -> RE -> DG/CNAT -> DIATINF
        cls.records['setor_diatinf'], cls.records['setor_diatinf_siape'] = cls.cadastrar_setor('DIATINF', cls.records['setor_dg_cnat'])

    @classmethod
    def _criar_usuarios_e_permissoes(cls):
        # `Situacao` e `CargoEmprego` vinham do seed do `suap_data`; agora das factories do `rh`.
        situacao_ativo_permanente = SituacaoFactory()
        jornada_trabalho_40h, _ = JornadaTrabalho.objects.get_or_create(codigo='40', defaults={'nome': '40h', 'excluido': False})
        jornada_trabalho_de, _ = JornadaTrabalho.objects.get_or_create(codigo='99', defaults={'nome': 'DE', 'excluido': False})
        cargo_emprego_professor = CargoEmpregoFactory()
        cargo_emprego_tae = cargo_emprego_professor

        # Criando atividades das funções
        funcao_atividade_reitor = cls.cadastrar(Atividade, data={'codigo': Atividade.REITOR, 'nome': 'Reitor'}, chaves={'codigo': Atividade.REITOR})
        funcao_atividade_diretor_geral = cls.cadastrar(
            Atividade, data={'codigo': Atividade.DIRETOR_GERAL, 'nome': 'Diretor Geral'}, chaves={'codigo': Atividade.DIRETOR_GERAL}
        )
        funcao_atividade_diretor = cls.cadastrar(
            Atividade, data={'codigo': Atividade.DIRETOR, 'nome': 'Diretor'}, chaves={'codigo': Atividade.DIRETOR}
        )
        funcao_atividade_chefe = cls.cadastrar(Atividade, data={'codigo': '0006', 'nome': 'Chefe de Gabinete'}, chaves={'codigo': '0006'})
        funcao_atividade_coordenador = cls.cadastrar(Atividade, data={'codigo': '2038', 'nome': 'Coordenador'}, chaves={'codigo': '2038'})
        funcao_cd = cls.cadastrar(Funcao, data={'codigo': Funcao.CODIGO_CD, 'nome': 'CD'}, chaves={'codigo': Funcao.CODIGO_CD})
        funcao_fg = cls.cadastrar(Funcao, data={'codigo': Funcao.CODIGO_FG, 'nome': 'FG'}, chaves={'codigo': Funcao.CODIGO_FG})

        agora = datetime.now(UTC)

        data = {
            'nome': 'reitor',
            'matricula': '9001',
            'ativo': True,
            'cpf': '321.309.510-90',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_professor,
            'setor': cls.records['setor_re'],
            'setor_lotacao': cls.records['setor_dg_cnat_siape'],  # setor siap DG
            'setor_exercicio': cls.records['setor_re_siap'],  # setor siap RE
            'setor_funcao': cls.records['setor_re_siap'],
            'jornada_trabalho': jornada_trabalho_de,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_reitor,
            'funcao': funcao_cd,
            'funcao_codigo': '0001',
        }
        cls.records['reitor'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9001'})

        data = {
            'servidor': cls.records['reitor'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_reitor,
            'funcao': funcao_cd,
            'nivel': '10',
            'setor': cls.records['setor_re_siap'],
            'setor_suap': cls.records['setor_re'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        data = {
            'nome': 'Diretor Geral CNAT',
            'matricula': '9002',
            'ativo': True,
            'cpf': '444.096.410-93',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_professor,
            'setor': cls.records['setor_dg_cnat'],
            'setor_lotacao': cls.records['setor_dg_cnat_siape'],
            'setor_exercicio': cls.records['setor_dg_cnat_siape'],
            'setor_funcao': cls.records['setor_dg_cnat_siape'],
            'jornada_trabalho': jornada_trabalho_de,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_diretor_geral,
            'funcao': funcao_cd,
            'funcao_codigo': '0002',
        }
        cls.records['diretor_cnat'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9002'})

        data = {
            'servidor': cls.records['diretor_cnat'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_diretor_geral,
            'funcao': funcao_cd,
            'nivel': '10',
            'setor': cls.records['setor_dg_cnat_siape'],
            'setor_suap': cls.records['setor_dg_cnat'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        data = {
            'nome': 'Diretor DIGTI',
            'matricula': '9003',
            'ativo': True,
            'cpf': '739.096.190-29',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_professor,
            'setor': cls.records['setor_digti'],
            'setor_lotacao': cls.records['setor_diatinf_siape'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'setor_funcao': cls.records['setor_digti_siap'],
            'jornada_trabalho': jornada_trabalho_de,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_diretor,
            'funcao': funcao_cd,
            'funcao_codigo': '0003',
        }
        cls.records['diretor_digti'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9003'})

        data = {
            'servidor': cls.records['diretor_digti'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_diretor,
            'funcao': funcao_cd,
            'nivel': '10',
            'setor': cls.records['setor_digti_siap'],
            'setor_suap': cls.records['setor_digti'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        data = {
            'nome': 'Chefe de gabinete',
            'matricula': '9004',
            'ativo': True,
            'cpf': '802.837.220-10',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_tae,
            'setor': cls.records['setor_gabin'],
            'setor_lotacao': cls.records['setor_re_siap'],
            'setor_exercicio': cls.records['setor_gabin_siap'],
            'setor_funcao': cls.records['setor_gabin_siap'],
            'jornada_trabalho': jornada_trabalho_40h,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_chefe,
            'funcao': funcao_cd,
            'funcao_codigo': '0003',
        }
        cls.records['chefe_gabin'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9004'})
        permissoes = Permission.objects.filter(
            codename__in=[
                'add_tipodocumento',
                'change_tipodocumento',
                'change_tipodocumento',
                'delete_tipodocumento',
                'add_tipodocumentotexto',
                'change_tipodocumentotexto',
                'change_tipodocumentotexto',
                'delete_tipodocumentotexto',
                'add_classificacao',
                'change_classificacao',
                'add_modelodocumento',
                'change_modelodocumento',
                'change_modelodocumento',
                'delete_modelodocumento',
            ]
        )
        user = cls.records['chefe_gabin'].get_user()
        for permissao in permissoes:
            user.user_permissions.add(permissao)

        data = {
            'servidor': cls.records['chefe_gabin'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_chefe,
            'funcao': funcao_cd,
            'nivel': '10',
            'setor': cls.records['setor_gabin_siap'],
            'setor_suap': cls.records['setor_gabin'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        # obj.user.groups.add(Group.objects.get(name=GRUPO_GERENTE_SISTEMICO))
        # obj.user.save()

        # Criando os coordenadores dos setores

        data = {
            'nome': 'Coordenador COSINF',
            'matricula': '9005',
            'ativo': True,
            'cpf': '459.822.330-80',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_tae,
            'setor': cls.records['setor_cosinf'],
            'setor_lotacao': cls.records['setor_re_siap'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'setor_funcao': cls.records['setor_digti_siap'],
            'jornada_trabalho': jornada_trabalho_40h,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_coordenador,
            'funcao': funcao_cd,
            'funcao_codigo': '0004',
        }
        cls.records['coord_cosinf'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9005'})

        data = {
            'servidor': cls.records['coord_cosinf'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_coordenador,
            'funcao': funcao_cd,
            'nivel': '10',
            'setor': cls.records['setor_digti_siap'],
            'setor_suap': cls.records['setor_cosinf'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        data = {
            'nome': 'Coordenador COSAAD',
            'matricula': '9006',
            'ativo': True,
            'cpf': '730.866.830-40',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_tae,
            'setor': cls.records['setor_cosaad'],
            'setor_lotacao': cls.records['setor_re_siap'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'setor_funcao': cls.records['setor_digti_siap'],
            'jornada_trabalho': jornada_trabalho_40h,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_coordenador,
            'funcao': funcao_fg,
            'funcao_codigo': '0001',
        }
        cls.records['coord_cosaad'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9006'})

        data = {
            'servidor': cls.records['coord_cosaad'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_coordenador,
            'funcao': funcao_fg,
            'nivel': '10',
            'setor': cls.records['setor_digti_siap'],
            'setor_suap': cls.records['setor_cosaad'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        # Criando os servidores da COSINF
        data = {
            'nome': 'Servidor COSINF1',
            'matricula': '9007',
            'ativo': True,
            'cpf': '418.105.140-45',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_tae,
            'setor': cls.records['setor_cosinf'],
            'setor_lotacao': cls.records['setor_re_siap'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'jornada_trabalho': jornada_trabalho_40h,
            'cargo_emprego_data_ocupacao': agora,
        }
        cls.records['scosinf1'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9007'})

        data = {
            'nome': 'Servidor COSINF2',
            'matricula': '9008',
            'template': b'1',
            'ativo': True,
            'cpf': '282.668.500-70',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_tae,
            'setor': cls.records['setor_cosinf'],
            'setor_lotacao': cls.records['setor_re_siap'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'email': 'sconsif2@mail.gov',
            'jornada_trabalho': jornada_trabalho_40h,
            'cargo_emprego_data_ocupacao': agora,
        }
        cls.records['scosinf2'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9008'})

        data = {
            'nome': 'Prestador COSINF3',
            'cpf': '738.738.738-93',
            'template': b'1',
            'email': 'sconsif3@mail.gov',
        }
        pessoa = cls.cadastrar(PessoaFisica, data, chaves={'cpf': '738.738.738-93'})
        data = {'setor': cls.records['setor_cosinf'], 'setor_lotacao': cls.records['setor_re_siap'], 'pessoa_fisica': pessoa, 'ativo': True}
        cls.records['pcosinf3'] = cls.cadastrar(PrestadorServico, data, chaves={'matricula': '9098'})

        # Criando os servidores da DIATINF
        data = {
            'nome': 'Servidor DIATINF',
            'matricula': '9009',
            'template': b'1',
            'ativo': True,
            'cpf': '345.828.290-40',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_professor,
            'setor': cls.records['setor_diatinf'],
            'setor_lotacao': cls.records['setor_dg_cnat_siape'],
            'setor_exercicio': cls.records['setor_diatinf_siape'],
            'email': 'sdiatinf1@mail.gov',
            'jornada_trabalho': jornada_trabalho_de,
            'cargo_emprego_data_ocupacao': agora,
        }
        cls.records['sdiatinf1'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9009'})

        # Criando os servidores da COINRE
        data = {
            'nome': 'Servidor COINRE 1',
            'matricula': '9010',
            'template': b'1',
            'ativo': True,
            'cpf': '841.587.250-03',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_tae,
            'setor': cls.records['setor_coinre'],
            'setor_lotacao': cls.records['setor_re_siap'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'email': 'scoinre1@mail.gov',
            'jornada_trabalho': jornada_trabalho_40h,
            'cargo_emprego_data_ocupacao': agora,
        }
        cls.records['scoinre1'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9010'})

        data = {
            'nome': 'Servidor COINRE 2',
            'matricula': '9011',
            'template': b'1',
            'ativo': True,
            'cpf': '435.771.410-93',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_tae,
            'setor': cls.records['setor_coinre'],
            'setor_lotacao': cls.records['setor_re_siap'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'email': 'scoinre2@mail.gov',
            'jornada_trabalho': jornada_trabalho_40h,
            'cargo_emprego_data_ocupacao': agora,
        }
        cls.records['scoinre2'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9011'})

        # Pro-reitor PROEX
        data = {
            'nome': 'Pro-reitor PROEX',
            'matricula': '9012',
            'template': b'1',
            'ativo': True,
            'cpf': '489.611.040-47',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_professor,
            'setor': cls.records['setor_proex'],
            'setor_lotacao': cls.records['setor_dg_cnat_siape'],
            'setor_exercicio': cls.records['setor_proex_siap'],
            'setor_funcao': cls.records['setor_proex_siap'],
            'email': 'proreitor_proex@mail.gov',
            'jornada_trabalho': jornada_trabalho_de,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_diretor,
            'funcao': funcao_cd,
            'funcao_codigo': '0002',
        }
        cls.records['proreitor_proex'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9012'})

        data = {
            'servidor': cls.records['proreitor_proex'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_diretor,
            'funcao': funcao_cd,
            'nivel': '10',
            'setor': cls.records['setor_proex_siap'],
            'setor_suap': cls.records['setor_proex'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        # Pro-reitor PROPI
        data = {
            'nome': 'Pro-reitor PROPI',
            'matricula': '9013',
            'template': b'1',
            'ativo': True,
            'cpf': '987.114.070-34',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_professor,
            'setor': cls.records['setor_propi'],
            'setor_lotacao': cls.records['setor_dg_cnat_siape'],
            'setor_exercicio': cls.records['setor_propi_siap'],
            'setor_funcao': cls.records['setor_propi_siap'],
            'email': 'proreitor_proex@mail.gov',
            'jornada_trabalho': jornada_trabalho_de,
            'cargo_emprego_data_ocupacao': agora,
            'funcao_atividade': funcao_atividade_diretor,
            'funcao': funcao_cd,
            'funcao_codigo': '0002',
        }
        cls.records['proreitor_propi'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9013'})

        data = {
            'servidor': cls.records['proreitor_propi'],
            'data_inicio_funcao': datetime.today(),
            'data_fim_funcao': None,
            'atividade': funcao_atividade_diretor,
            'funcao': funcao_cd,
            'nivel': '10',
            'setor': cls.records['setor_propi_siap'],
            'setor_suap': cls.records['setor_propi'],
        }
        cls.cadastrar(ServidorFuncaoHistorico, data)

        # Criando os servidores da DIATINF
        data = {
            'nome': 'Servidor DIGTI',
            'matricula': '9014',
            'template': b'1',
            'ativo': True,
            'cpf': '106.312.880-31',
            'situacao': situacao_ativo_permanente,
            'cargo_emprego': cargo_emprego_professor,
            'setor': cls.records['setor_digti'],
            'setor_lotacao': cls.records['setor_dg_cnat_siape'],
            'setor_exercicio': cls.records['setor_digti_siap'],
            'email': 'sdigti1@mail.gov',
            'jornada_trabalho': jornada_trabalho_de,
            'cargo_emprego_data_ocupacao': agora,
        }
        cls.records['sdigti1'] = cls.cadastrar(Servidor, data, chaves={'matricula': '9014'})

        data = {
            'nome': 'Interrupção de Férias',
            'permite_nivel_acesso_privado': True,
            'permite_nivel_acesso_restrito': True,
            'permite_nivel_acesso_publico': True,
            'nivel_acesso_default': 3,
        }
        cls.records['tipo_processo'] = cls.cadastrar(TipoProcesso, data, chaves={'nome': 'Interrupção de Férias'})

        data = {'nivel_acesso': 'Público', 'descricao': 'Hipótese Legal Pública', 'base_legal': 'Art. 26'}
        cls.records['hipotese_legal_publico'] = cls.cadastrar(HipoteseLegal, data, chaves={'descricao': 'Hipótese Legal Pública'})

        data = {'nivel_acesso': 'Restrito', 'descricao': 'Hipótese Legal Restrita', 'base_legal': 'Art. 27'}
        cls.records['hipotese_legal_restrito'] = cls.cadastrar(HipoteseLegal, data, chaves={'descricao': 'Hipótese Legal Restrita'})

        data = {'nivel_acesso': 'Sigiloso', 'descricao': 'Hipótese Legal Sigilosa', 'base_legal': 'Art. 28'}
        cls.records['hipotese_legal_sigiloso'] = cls.cadastrar(HipoteseLegal, data, chaves={'descricao': 'Hipótese Legal Sigilosa'})

        ModeloDespacho.objects.create(cabecalho='----', rodape='----')

        if not Papel.objects.filter(vinculo=cls.records['reitor'].get_vinculo()).exists():
            # Cadastrando os papeis dos servidores
            from rh.management.commands.importar_funcao_servidor import Command

            comando_cadastrar_papel = Command()
            comando_cadastrar_papel.handle()

        for tipo in TipoDocumentoTexto.objects.all():
            tipo.save()

        for obj in list(cls.records.values()):
            if isinstance(obj, Servidor):
                logger.info(f'Adicionando servidor {obj} no grupo {GRUPO_OPERADOR_DOCUMENTO}')
                user = obj.get_user()
                user.groups.add(Group.objects.get(name=GRUPO_OPERADOR_DOCUMENTO))
                user.save()

    def test_documentos_respeitam_permissoes_por_estado_nivel_de_acesso_e_compartilhamento(self, client):
        self._adicionar_permissoes(client)
        self._verificar_setores_compartilhados()

        client.login(username=self.records['coord_cosinf'].get_user().username, password='123')
        self._criar_documentos(client)

        self._tem_permissao_ler()
        self._tem_permissao_estrita_leitura()
        self._tem_permissao_editar()
        self._pode_editar()
        self._pode_concluir_documento()

    @classmethod
    def _adicionar_permissoes(cls, client):
        user = cls.records['coord_cosinf'].get_user()
        client.logout()
        client.login(username=user.username, password='123')

        data = {
            'setores_permitidos_podem_escrever': [cls.records['setor_digti'].id],
            'pessoas_permitidas_podem_escrever': [cls.records['scosinf1'].get_vinculo().id],
            'setores_permitidos_podem_ler': [cls.records['setor_cosaad'].id],
            'pessoas_permitidas_podem_ler': [cls.records['scosinf2'].get_vinculo().id],
        }

        client.post('/documento_eletronico/gerenciar_compartilhamento_setor/', data)

    @classmethod
    def _verificar_setores_compartilhados(cls):
        def setor_editar_compartilhado_usuario(user):
            return get_setores_compartilhados(user, NivelPermissao.EDITAR).order_by('id').values_list('id', flat=True)

        def setor_ler_compartilhado_usuario(user):
            return get_setores_compartilhados(user, NivelPermissao.LER).order_by('id').values_list('id', flat=True)

        assert cls.records['setor_cosinf'].id in setor_editar_compartilhado_usuario(cls.records['coord_cosinf'].get_user())
        # servidor cosaad ta compartilhado leitura pela cosinf
        assert cls.records['setor_cosaad'].id in setor_editar_compartilhado_usuario(cls.records['coord_cosaad'].get_user())
        assert all(
            setor in setor_editar_compartilhado_usuario(cls.records['diretor_digti'].get_user())
            for setor in [cls.records['setor_digti'].id, cls.records['setor_cosinf'].id]
        )
        assert cls.records['setor_cosinf'].id in setor_editar_compartilhado_usuario(cls.records['scosinf1'].get_user())
        assert not setor_editar_compartilhado_usuario(cls.records['scosinf2'].get_user()).exists()
        assert not setor_editar_compartilhado_usuario(cls.records['pcosinf3'].get_user()).exists()
        assert cls.records['setor_proex'].id in setor_editar_compartilhado_usuario(cls.records['proreitor_proex'].get_user())
        assert cls.records['setor_propi'].id in setor_editar_compartilhado_usuario(cls.records['proreitor_propi'].get_user())

        assert cls.records['setor_cosinf'].id in setor_ler_compartilhado_usuario(cls.records['coord_cosinf'].get_user())
        assert all(
            setor in setor_ler_compartilhado_usuario(cls.records['coord_cosaad'].get_user())
            for setor in [cls.records['setor_cosinf'].id, cls.records['setor_cosaad'].id]
        )
        assert cls.records['setor_digti'].id in setor_ler_compartilhado_usuario(cls.records['diretor_digti'].get_user())
        assert not setor_ler_compartilhado_usuario(cls.records['scosinf1'].get_user()).exists()
        assert cls.records['setor_cosinf'].id in setor_ler_compartilhado_usuario(cls.records['scosinf2'].get_user())
        assert not setor_ler_compartilhado_usuario(cls.records['pcosinf3'].get_user()).exists()
        assert cls.records['setor_proex'].id in setor_ler_compartilhado_usuario(cls.records['proreitor_proex'].get_user())
        assert cls.records['setor_propi'].id in setor_ler_compartilhado_usuario(cls.records['proreitor_propi'].get_user())

    @classmethod
    def _criar_documentos(cls, client):
        # Documento Rascunho Público
        cls.records['documento_rascunho_publico'] = cls._gerar_documento(client, 'Rascunho Público', Documento.NIVEL_ACESSO_PUBLICO)

        # Documento Compartilhado Público
        cls.records['documento_compartilhado_publico'] = cls._gerar_documento(client, 'Compartilhado Público', Documento.NIVEL_ACESSO_PUBLICO)

        cls._gerar_compartilhamento(client, cls.records['documento_compartilhado_publico'])

        # Documento Concluído Público
        cls.records['documento_concluido_publico'] = cls._gerar_documento(client, 'Concluído Público', Documento.NIVEL_ACESSO_PUBLICO)
        cls._gerar_compartilhamento(client, cls.records['documento_concluido_publico'])
        cls._concluir_documento(client, cls.records['documento_concluido_publico'])
        # Documento Concluído Público
        cls.records['documento_finalizado_publico'] = cls._gerar_documento(client, 'Finalizado Público', Documento.NIVEL_ACESSO_PUBLICO)
        cls._gerar_compartilhamento(client, cls.records['documento_finalizado_publico'])
        cls._finalizar_documento(client, cls.records['documento_finalizado_publico'])

        # Documento Rascunho Restrito
        cls.records['documento_rascunho_restrito'] = cls._gerar_documento(client, 'Rascunho Restrito', Documento.NIVEL_ACESSO_RESTRITO)

        # Documento Compartilhado Restrito
        cls.records['documento_compartilhado_restrito'] = cls._gerar_documento(client, 'Compartilhado Restrito', Documento.NIVEL_ACESSO_RESTRITO)
        cls._gerar_compartilhamento(client, cls.records['documento_compartilhado_restrito'])

        # Documento Concluído Restrito
        cls.records['documento_concluido_restrito'] = cls._gerar_documento(client, 'Concluído Restrito', Documento.NIVEL_ACESSO_RESTRITO)
        cls._gerar_compartilhamento(client, cls.records['documento_concluido_restrito'])
        cls._concluir_documento(client, cls.records['documento_concluido_restrito'])

        # Documento Concluído Restrito
        cls.records['documento_finalizado_restrito'] = cls._gerar_documento(client, 'Finalizado Restrito', Documento.NIVEL_ACESSO_RESTRITO)
        cls._gerar_compartilhamento(client, cls.records['documento_finalizado_restrito'])
        cls._finalizar_documento(client, cls.records['documento_finalizado_restrito'])

        # Documento Rascunho Sigiloso
        cls.records['documento_rascunho_sigiloso'] = cls._gerar_documento(client, 'Rascunho Sigiloso', Documento.NIVEL_ACESSO_SIGILOSO)

        # Documento Compartilhado Sigiloso
        cls.records['documento_compartilhado_sigiloso'] = cls._gerar_documento(client, 'Compartilhado Sigiloso', Documento.NIVEL_ACESSO_SIGILOSO)
        cls._gerar_compartilhamento(client, cls.records['documento_compartilhado_sigiloso'])

        # Documento Concluído Sigiloso
        cls.records['documento_concluido_sigiloso'] = cls._gerar_documento(client, 'Concluído Sigiloso', Documento.NIVEL_ACESSO_SIGILOSO)
        cls._gerar_compartilhamento(client, cls.records['documento_concluido_sigiloso'])
        cls._concluir_documento(client, cls.records['documento_concluido_sigiloso'])

        # Documento Concluído Sigiloso
        cls.records['documento_finalizado_sigiloso'] = cls._gerar_documento(client, 'Finalizado Sigiloso', Documento.NIVEL_ACESSO_SIGILOSO)
        cls._gerar_compartilhamento(client, cls.records['documento_finalizado_sigiloso'])
        cls._finalizar_documento(client, cls.records['documento_finalizado_sigiloso'])

        # Documento Processo Público
        cls.records['documento_processo_publico'] = cls._gerar_documento(client, 'Processo Público', Documento.NIVEL_ACESSO_PUBLICO)
        cls._gerar_compartilhamento(client, cls.records['documento_processo_publico'])
        cls._finalizar_documento(client, cls.records['documento_processo_publico'])
        cls._criar_processo(client, cls.records['documento_processo_publico'], Processo.NIVEL_ACESSO_PUBLICO)

        # Documento Processo Restrito
        cls.records['documento_processo_restrito'] = cls._gerar_documento(client, 'Processo Restrito', Documento.NIVEL_ACESSO_RESTRITO)
        cls._gerar_compartilhamento(client, cls.records['documento_processo_restrito'])
        cls._finalizar_documento(client, cls.records['documento_processo_restrito'])
        cls._criar_processo(client, cls.records['documento_processo_restrito'], Processo.NIVEL_ACESSO_RESTRITO)

        # Documento Processo Sigiloso
        cls.records['documento_processo_sigiloso'] = cls._gerar_documento(client, 'Processo Sigiloso', Documento.NIVEL_ACESSO_SIGILOSO)
        cls._gerar_compartilhamento(client, cls.records['documento_processo_sigiloso'])
        cls._finalizar_documento(client, cls.records['documento_processo_sigiloso'])
        cls._criar_processo(client, cls.records['documento_processo_sigiloso'], Processo.NIVEL_ACESSO_PRIVADO)

    @classmethod
    def _gerar_documento(cls, client, assunto, nivel_acesso):
        if DocumentoTexto.objects.filter(assunto=assunto).exists():
            return DocumentoTexto.objects.filter(assunto=assunto)[0]
        oficio = TipoDocumentoTexto.objects.get(sigla='OFÍCIO')
        setor = cls.records['scosinf1'].setor
        modelo_documento = oficio.modelos.all()[0]

        # oficio.get_sugestao_identificador_definitivo(tipo_documento_texto=oficio, setor_dono=setor)

        data = {
            'tipo': oficio.id,
            'modelo': modelo_documento.id,
            'nivel_acesso': nivel_acesso,
            'setor_dono': setor.id,
            'assunto': f'Documento {assunto}',
        }
        # Verifica se aparece o botão "Adicionar"
        client.post('/admin/documento_eletronico/documentotexto/add/', data)
        documento = DocumentoTexto.objects.latest('id')
        return documento

    @classmethod
    def _gerar_compartilhamento(cls, client, documento):
        data = {
            'pessoas_permitidas_podem_ler': [cls.records['proreitor_propi'].get_vinculo().id],
            'pessoas_permitidas_podem_escrever': [cls.records['diretor_cnat'].get_vinculo().id],
            'setores_permitidos_podem_ler': [cls.records['setor_proex'].id],
            'setores_permitidos_podem_escrever': [cls.records['setor_gabin'].id],
        }
        url = f'/documento_eletronico/gerenciar_compartilhamento_documento/{documento.id}/'
        client.post(url, data, follow=True)

    @classmethod
    def _concluir_documento(cls, client, documento):
        url = f'/documento_eletronico/concluir_documento/{documento.id}/'
        client.get(url, follow=True)

    @classmethod
    def _assinar_documento(cls, client, documento):
        url = f'/documento_eletronico/assinar_documento/{documento.id}/'
        identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla = (
            documento.get_sugestao_identificador_definitivo(
                tipo_documento_texto=documento.modelo.tipo_documento_texto, setor_dono=documento.setor_dono
            )
        )
        # determina dinamicamente o primeiro papel disponível para o usuário logado no `client`
        papel_id = None
        try:
            session = client.session
            user_id = session.get('_auth_user_id')
            if user_id:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.get(pk=user_id)
                vinculo = user.get_relacionamento()
                papeis = getattr(vinculo, 'papeis_ativos', None)
                if papeis is not None:
                    primeiro = papeis.first()
                    if primeiro:
                        papel_id = primeiro.id
        except Exception:
            # se qualquer coisa falhar, manter o comportamento anterior (valor literal)
            papel_id = None

        data = {
            'assinar_documento_senha_wizard-current_step': '0',
            '0-identificador_tipo_documento_sigla': identificador_tipo_documento_sigla,
            '0-identificador_numero': identificador_numero,
            '0-identificador_ano': identificador_ano,
            '0-identificador_setor_sigla': identificador_setor_sigla,
            '1-senha': '123',
            '1-papel': str(papel_id) if papel_id is not None else '6',
        }
        response = client.post(url, data, follow=True)
        assert 'Assinar Documento' in response.content.decode()
        data['assinar_documento_senha_wizard-current_step'] = '1'
        response = client.post(url, data, follow=True)
        assert 'Documento assinado com sucesso.' in response.content.decode()

    @classmethod
    def _finalizar_documento(cls, client, documento):
        cls._concluir_documento(client, documento)
        cls._assinar_documento(client, documento)

        url = f'/documento_eletronico/finalizar_documento/{documento.id}/'
        client.get(url, follow=True)

    @classmethod
    def _criar_processo(cls, client, documento, nivel_acesso):
        url = f'/admin/processo_eletronico/processo/add/?documento_id={documento.id}'

        if nivel_acesso == Processo.NIVEL_ACESSO_PRIVADO:
            nivel_acesso_str = 'sigiloso'
        elif nivel_acesso == Processo.NIVEL_ACESSO_RESTRITO:
            nivel_acesso_str = 'restrito'
        else:
            nivel_acesso_str = 'publico'

        data = {
            'interessados': [cls.records['sdiatinf1'].get_vinculo().id],
            'tipo_processo': cls.records['tipo_processo'].id,
            'assunto': 'Interrupção de Férias',
            'nivel_acesso': nivel_acesso,
            'hipotese_legal': cls.records[f'hipotese_legal_{nivel_acesso_str}'].id,
            'setor_criacao': cls.records['setor_cosinf'].id,
        }
        response = client.post(url, data, follow=True)
        processo_id = response.request['PATH_INFO'].split('/')[3]
        url = f'/processo_eletronico/processo/encaminhar_sem_despacho/{processo_id}/'

        data = {'tipo_busca_setor': 'autocompletar', 'destinatario_setor_autocompletar': cls.records['setor_diatinf'].id}
        response = client.post(url, data, follow=True)

        client2 = type(client)()
        client2.login(username=cls.records['sdiatinf1'].get_user().username, password='123')
        url = f'/processo_eletronico/processo/receber/{processo_id}/'
        response = client2.get(url, follow=True)

    @pytest.fixture(autouse=True)
    def _auto_setup(self, _montar_dados):
        # Pede `_montar_dados` para fixar a ordem: ambas são autouse e de função, e esta
        # só copia para a instância o que aquela acabou de montar na classe.
        self.records = TestPermissoesDocumentoEletronico.records
        self.servidores = []
        for obj in list(self.records.values()):
            if isinstance(obj, Servidor):
                self.servidores.append(obj)

    @classmethod
    def _tem_permissao_ler(cls):
        data = {
            'documento_rascunho_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_concluido_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_concluido_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_concluido_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_finalizado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_processo_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
                ['sdiatinf1', False],
            ],
            # Rever esse teste porque o documento
            # tem um compartilhamento e esse teste é
            # inócuo.
            'documento_processo_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', True],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', True],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
                ['sdiatinf1', True],
            ],
            'documento_processo_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
                ['sdiatinf1', False],
            ],
        }
        for chave, lista in data.items():
            for usuario, resultado in lista:
                assert_permissao_documento(chave, usuario, 'ler', cls.records[chave].pode_ler(cls.records[usuario].get_user()), resultado)

    @classmethod
    def _tem_permissao_estrita_leitura(cls):
        data = {
            'documento_rascunho_publico': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_publico': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_concluido_publico': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_publico': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_restrito': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_restrito': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_concluido_restrito': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_restrito': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_sigiloso': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_sigiloso': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_concluido_sigiloso': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_finalizado_sigiloso': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_processo_publico': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
                ['sdiatinf1', False],
            ],
            'documento_processo_restrito': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', True],
                ['chefe_gabin', True],
                ['sdiatinf1', False],
            ],
            'documento_processo_sigiloso': [
                ['coord_cosinf', False],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', True],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
                ['sdiatinf1', False],
            ],
        }

        for chave, lista in data.items():
            for usuario, resultado in lista:
                user = cls.records[usuario]
                assert_permissao_documento(
                    chave,
                    usuario,
                    'ler por compartilhamento explícito',
                    cls.records[chave].tem_permissao_estrita_leitura(user.get_vinculo()),
                    resultado,
                )

    @classmethod
    def _tem_permissao_editar(cls):
        data = {
            'documento_rascunho_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_concluido_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_concluido_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_concluido_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_finalizado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_processo_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
                ['sdiatinf1', False],
            ],
            'documento_processo_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
                ['sdiatinf1', False],
            ],
            'documento_processo_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
                ['sdiatinf1', False],
            ],
        }

        for chave, lista in data.items():
            for usuario, resultado in lista:
                assert_permissao_documento(
                    chave,
                    usuario,
                    'editar',
                    cls.records[chave].tem_permissao_editar(cls.records[usuario].get_user()),
                    resultado,
                )

    @classmethod
    def _pode_editar(cls):
        data = {
            'documento_rascunho_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_concluido_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_concluido_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_concluido_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_finalizado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_processo_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
                ['sdiatinf1', False],
            ],
            'documento_processo_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
                ['sdiatinf1', False],
            ],
            'documento_processo_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
                ['sdiatinf1', False],
            ],
        }

        for chave, lista in data.items():
            for usuario, resultado in lista:
                assert_permissao_documento(
                    chave,
                    usuario,
                    'editar pela regra completa',
                    cls.records[chave].pode_editar(cls.records[usuario].get_user()),
                    resultado,
                )

    @classmethod
    def _pode_concluir_documento(cls):
        data = {
            'documento_rascunho_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_concluido_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_concluido_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_finalizado_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_rascunho_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', False],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_compartilhado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_concluido_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_finalizado_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
            'documento_processo_publico': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_processo_restrito': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', True],
                ['scosinf1', True],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', True],
            ],
            'documento_processo_sigiloso': [
                ['coord_cosinf', True],
                ['coord_cosaad', False],
                ['diretor_digti', False],
                ['scosinf1', False],
                ['scosinf2', False],
                ['pcosinf3', False],
                ['proreitor_propi', False],
                ['diretor_cnat', True],
                ['proreitor_proex', False],
                ['chefe_gabin', False],
            ],
        }

        for chave, lista in data.items():
            for usuario, resultado in lista:
                assert_permissao_documento(
                    chave,
                    usuario,
                    'concluir',
                    cls.records[chave].pode_concluir_documento(cls.records[usuario].get_user()),
                    resultado,
                )
