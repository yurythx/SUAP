import pytest
from django.contrib import admin
from django.test import RequestFactory

from comum.admin import PrestadorServicoAdmin
from comum.forms import PrestadorServicoForm
from comum.models import JustificativaUsuarioExterno, Pais, PrestadorServico, User
from comum.tests.factories import PrestadorServicoFactory
from rh.deduplicacao.documentos import MENSAGEM_PASSAPORTE_INVALIDO
from rh.enums import Nacionalidade
from rh.tests.factories import PessoaFisicaFactory, cpf_valido

pytestmark = pytest.mark.django_db


def _dados(**extra: object) -> dict:
    perfil = JustificativaUsuarioExterno.objects.create(justificativa='Visitante')
    return {
        'nome_registro': 'Ana Estrangeira',
        'sexo': 'F',
        'nacionalidade': Nacionalidade.ESTRANGEIRO,
        'passaporte': 'AB123456',
        'email_secundario': 'ana@exemplo.com',
        'confirma_email': 'ana@exemplo.com',
        'justificativa_cadastro': perfil.pk,
        **extra,
    }


def test_estrangeiro_sem_cpf_exige_pais() -> None:
    form = PrestadorServicoForm(data=_dados())

    assert not form.is_valid()
    assert 'pais_origem' in form.errors


def test_estrangeiro_com_pais_passa_na_validacao_do_documento() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    form = PrestadorServicoForm(data=_dados(pais_origem=argentina.pk))

    form.is_valid()
    assert 'pais_origem' not in form.errors
    assert 'passaporte' not in form.errors


def _prestador_estrangeiro(pais: Pais, cpf: str = '') -> PrestadorServico:
    pessoa = PessoaFisicaFactory(cpf=cpf, passaporte='AB123456', pais_origem=pais, nacionalidade=Nacionalidade.ESTRANGEIRO)
    return PrestadorServicoFactory(pessoa_fisica=pessoa, matricula=PrestadorServico.gerar_matricula(cpf) if cpf else 'AB123456')


@pytest.mark.parametrize('mesmo_pais', [True, False])
def test_passaporte_ja_usado_e_o_do_mesmo_pais(mesmo_pais: bool) -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    _prestador_estrangeiro(argentina if mesmo_pais else Pais.objects.create(codigo='158', nome='CHILE', iso_alfa3='CHL'), cpf=cpf_valido(901))
    form = PrestadorServicoForm(data=_dados(cpf=cpf_valido(902), pais_origem=argentina.pk))

    form.is_valid()
    assert ('Este passaporte já está sendo usado por outro prestador.' in form.errors.get('passaporte', [])) is mesmo_pais


def _cadastrar_pelo_admin(rf: RequestFactory, **extra: object) -> PrestadorServico:
    form = PrestadorServicoForm(data=_dados(**extra))
    assert form.is_valid(), form.errors
    prestador = PrestadorServico()
    PrestadorServicoAdmin(PrestadorServico, admin.site).save_model(rf.post('/'), prestador, form, False)
    return PrestadorServico.objects.get(pk=prestador.pk)


def test_mesmo_numero_de_outro_pais_sem_cpf_e_outra_pessoa_com_outro_login(rf: RequestFactory) -> None:
    """O login do estrangeiro sem CPF é a chave ISO + número: o mesmo número de dois países convive."""
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    chilena = _prestador_estrangeiro(Pais.objects.create(codigo='158', nome='CHILE', iso_alfa3='CHL'))

    argentina_nova = _cadastrar_pelo_admin(rf, pais_origem=argentina.pk, passaporte='ab-123.456')

    assert argentina_nova.pessoa_fisica_id != chilena.pessoa_fisica_id
    assert (argentina_nova.matricula, argentina_nova.get_user().username) == ('ARG-AB123456', 'ARG-AB123456')
    assert argentina_nova.pessoa_fisica.documento_identificador == 'ARG-AB123456'


def test_legado_mantem_o_login_so_com_o_numero(rf: RequestFactory) -> None:
    """Só o cadastro novo ganha a chave como login: o legado salvo de novo ou cadastrado outra vez segue com o seu."""
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    legado = _prestador_estrangeiro(argentina)
    # o legado entrou com o login só com o número do passaporte
    User.objects.filter(pk=legado.get_user().pk).update(username='AB123456')
    PrestadorServico.objects.filter(pk=legado.pk).update(matricula='AB123456')
    PrestadorServico.objects.get(pk=legado.pk).save()

    dados = {
        'pessoa_fisica': {
            'nome_registro': 'Ana Estrangeira',
            'nacionalidade': Nacionalidade.ESTRANGEIRO,
            'passaporte': 'AB123456',
            'pais_origem': argentina,
        }
    }
    recadastrado = PrestadorServico.update_or_create(dados, enviar_email=False)['prestador']

    assert recadastrado.pk == legado.pk
    assert (PrestadorServico.objects.get(pk=legado.pk).matricula, recadastrado.get_user().username) == ('AB123456', 'AB123456')
    assert PrestadorServico.objects.filter(pessoa_fisica=legado.pessoa_fisica).count() == 1


def test_admin_cadastra_estrangeiro_sem_cpf_com_o_pais(rf: RequestFactory) -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')

    prestador = _cadastrar_pelo_admin(rf, pais_origem=argentina.pk)

    assert (prestador.pessoa_fisica.passaporte, prestador.pessoa_fisica.pais_origem, prestador.matricula) == ('AB123456', argentina, 'ARG-AB123456')


def test_cpf_novo_com_passaporte_de_pessoa_com_outro_cpf_e_erro_no_passaporte() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    PessoaFisicaFactory(cpf=cpf_valido(903), passaporte='AB123456', pais_origem=argentina)

    form = PrestadorServicoForm(data=_dados(cpf=cpf_valido(904), pais_origem=argentina.pk))

    assert not form.is_valid()
    assert 'Passaporte já pertence a outra pessoa' in form.errors['passaporte']


def test_estrangeiro_sem_cpf_de_pais_sem_iso_e_erro_no_passaporte() -> None:
    sem_iso = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')

    form = PrestadorServicoForm(data=_dados(pais_origem=sem_iso.pk))

    assert not form.is_valid()
    assert 'País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países.' in form.errors['passaporte']


@pytest.mark.parametrize('passaporte', ['NÃO TENHO', '1111111'])
def test_estrangeiro_sem_cpf_com_passaporte_invalido_e_erro_no_passaporte(passaporte: str) -> None:
    """O ``save_model`` levantaria a recusa do ``obter_ou_criar`` como erro 500."""
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')

    form = PrestadorServicoForm(data=_dados(pais_origem=argentina.pk, passaporte=passaporte))

    assert not form.is_valid()
    assert MENSAGEM_PASSAPORTE_INVALIDO in form.errors['passaporte']


@pytest.mark.usefixtures('sync_permissions')
def test_dar_o_pais_ao_legado_sem_pais_edita_o_mesmo_prestador(rf: RequestFactory) -> None:
    """A edição que preenche o país do legado (login só o número) não cria outra pessoa nem outro prestador."""
    from rh.models import PessoaFisica
    from rh.tests.factories import ServidorFactory

    chile = Pais.objects.create(codigo='158', nome='CHILE', iso_alfa3='CHL')
    legado = _prestador_estrangeiro(chile)
    User.objects.filter(pk=legado.get_user().pk).update(username='AB123456')
    PrestadorServico.objects.filter(pk=legado.pk).update(matricula='AB123456')
    PessoaFisica.objects.filter(pk=legado.pessoa_fisica_id).update(
        pais_origem=None, documento_identificador=f'SEMPAIS-{legado.pessoa_fisica_id}-AB123456'
    )
    legado = PrestadorServico.objects.get(pk=legado.pk)
    request = rf.post('/')
    request.user = ServidorFactory().get_user()
    form = PrestadorServicoForm(data=_dados(pais_origem=chile.pk), instance=legado, request=request)
    form.data = {**form.data, 'nome_usual': form.fields['nome_usual'].choices[-1][0]}
    assert form.is_valid(), form.errors

    PrestadorServicoAdmin(PrestadorServico, admin.site).save_model(request, legado, form, True)

    assert list(PrestadorServico.objects.filter(pessoa_fisica__passaporte='AB123456').values_list('pk', 'matricula')) == [(legado.pk, 'AB123456')]
    pessoa = PrestadorServico.objects.get(pk=legado.pk).pessoa_fisica
    assert (pessoa.pais_origem, pessoa.documento_identificador) == (chile, 'CHL-AB123456')


@pytest.mark.usefixtures('sync_permissions')
def test_edicao_nao_troca_pais_nem_passaporte_nem_cria_outro_prestador(rf: RequestFactory) -> None:
    """Na edição, CPF, passaporte, país e nacionalidade são somente leitura, inclusive para o superusuário: trocar criaria outra pessoa."""
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    chile = Pais.objects.create(codigo='158', nome='CHILE', iso_alfa3='CHL')
    prestador = _cadastrar_pelo_admin(rf, pais_origem=argentina.pk)
    request = rf.post('/')
    request.user = User.objects.create_superuser('admin-teste', 'admin@exemplo.com', 'x')
    tentativa = _dados(pais_origem=chile.pk, passaporte='ZZ999999', cpf=cpf_valido(905), nacionalidade=Nacionalidade.BRASILEIRO_NATO)
    form = PrestadorServicoForm(data=tentativa, instance=prestador, request=request)
    form.data = {**form.data, 'nome_usual': form.fields['nome_usual'].choices[-1][0]}
    assert form.is_valid(), form.errors

    PrestadorServicoAdmin(PrestadorServico, admin.site).save_model(request, prestador, form, True)

    assert list(PrestadorServico.objects.values_list('pk', 'matricula')) == [(prestador.pk, 'ARG-AB123456')]
    pessoa = PrestadorServico.objects.get(pk=prestador.pk).pessoa_fisica
    assert (pessoa.cpf, pessoa.passaporte, pessoa.pais_origem, pessoa.nacionalidade, pessoa.documento_identificador) == (
        None,
        'AB123456',
        argentina,
        Nacionalidade.ESTRANGEIRO,
        'ARG-AB123456',
    )


@pytest.mark.usefixtures('sync_permissions')
def test_prestador_cuja_pessoa_foi_separada_continua_salvavel() -> None:
    """A separação tira o CPF da PF (CONFLITO-): o prestador mantém o login em vez de derivá-lo de um CPF vazio."""
    from rh.models import PessoaFisica

    prestador = PrestadorServicoFactory(pessoa_fisica=PessoaFisicaFactory(cpf=cpf_valido(906)))
    login = prestador.matricula
    PessoaFisica.objects.filter(pk=prestador.pessoa_fisica_id).update(cpf=None, documento_identificador=f'CONFLITO-1-{cpf_valido(906)}')
    prestador = PrestadorServico.objects.get(pk=prestador.pk)

    prestador.ativo = False
    prestador.save()

    assert PrestadorServico.objects.get(pk=prestador.pk).matricula == login
