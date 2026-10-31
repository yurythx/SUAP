import datetime
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.contenttypes.models import ContentType
from model_bakery import baker, random_gen

from comum.models import Configuracao
from comum.utils import get_sigla_reitoria
from djtools.middleware import threadlocals
from documento_eletronico import models as docs
from boletim_servico import models as boletim_models
from rh.models import Papel, Servidor, ServidorFuncaoHistorico
from rh.tests.factories import ServidorFactory, SetorFactory, SetorSiapeFactory, UnidadeOrganizacionalFactory, cpf_valido


def _mock_now():
    return datetime.datetime(2018, 8, 13)


@pytest.fixture(autouse=True)
def _configurar_generators_bakery(monkeypatch):
    """Registra os campos do SUAP no bakery, sem vazar para os outros módulos.

    ``baker.generators.add`` escreve no dicionário global ``generators.user_mapping``. Era uma
    fixture de sessão sem teardown, então as registros sobreviviam a este módulo: no worker que
    rodasse `boletim_servico` antes, `djtools/tests/.../test_banco_mock.py` via `CharFieldPlus`
    já mapeado para `gen_string` e `registrar_geradores` pulava o campo. Trocar o dicionário por
    uma cópia faz o ``monkeypatch`` restaurar o original no fim de cada teste — mesmo idioma do
    ``_isolar_geradores`` de ``djtools``.
    """
    monkeypatch.setattr(baker.generators, 'user_mapping', dict(baker.generators.user_mapping))
    baker.generators.add('djtools.db.models.CharFieldPlus', random_gen.gen_string)
    baker.generators.add('djtools.db.models.SearchField', random_gen.gen_text)
    baker.generators.add('djtools.db.models.ForeignKey', random_gen.gen_related)
    baker.generators.add('djtools.db.models.ForeignKeyPlus', random_gen.gen_related)
    baker.generators.add('djtools.db.models.DateFieldPlus', random_gen.gen_date)
    baker.generators.add('djtools.db.models.DateTimeFieldPlus', random_gen.gen_datetime)
    baker.generators.add('djtools.db.models.TimeFieldPlus', random_gen.gen_time)
    baker.generators.add('djtools.db.models.OneToOneFieldPlus', random_gen.gen_related)
    baker.generators.add('djtools.db.models.OneToOneField', random_gen.gen_related)
    baker.generators.add('djtools.db.models.ManyToManyFieldPlus', random_gen.gen_m2m)
    baker.generators.add('djtools.db.models.CurrentUserField', random_gen.gen_related)
    baker.generators.add('djtools.db.models.DecimalFieldPlus', random_gen.gen_decimal)
    baker.generators.add('djtools.db.models.FileFieldPlus', random_gen.gen_file_field)
    baker.generators.add('djtools.db.models.fields.unaccent.UnaccentField', random_gen.gen_string)


@pytest.fixture(autouse=True)
def _mock_timezone_now(monkeypatch):
    monkeypatch.setattr('django.utils.timezone.now', _mock_now)


@pytest.fixture(autouse=True)
def _set_celery_eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True


@pytest.fixture
def estrutura(db, sync_permissions):
    """Reitoria (setor raiz) e um campus A0 sob ela.

    A sigla do setor raiz é a da reitoria (`get_sigla_reitoria`, default `RE`) porque o
    cabeçalho de todo documento resolve `UnidadeOrganizacional.objects.suap().get(sigla=...)`
    — sem essa unidade, salvar um DocumentoTexto estoura `DoesNotExist`.

    A0 tem campus PRÓPRIO: o `uo` é herdado do superior, então sem criar a unidade dele
    explicitamente A0 ficaria no campus da reitoria — que é onde mora o reitor.
    """
    Configuracao.objects.get_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'IFRN'})

    setor_raiz_suap = SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria')
    setor_raiz_siape = SetorSiapeFactory(sigla='RAIZ')
    setor_a0_suap = SetorFactory(sigla='A0', superior=setor_raiz_suap)
    UnidadeOrganizacionalFactory(setor=setor_a0_suap, sigla='A0', nome='A0')
    setor_a0_suap.refresh_from_db()

    return SimpleNamespace(raiz_suap=setor_raiz_suap, raiz_siape=setor_raiz_siape, a0_suap=setor_a0_suap)


@pytest.fixture
def dados_boletim(rf, estrutura):
    setor_raiz_suap = estrutura.raiz_suap
    setor_raiz_siape = estrutura.raiz_siape
    setor_a0_suap = estrutura.a0_suap
    # O servidor assina os documentos do boletim; o `template` do rosto entra na assinatura.
    servidor_a = ServidorFactory(setor=setor_a0_suap, pessoa_fisica__template=b'1')

    reitor = baker.make(
        Servidor,
        pessoa_fisica__template=b'1',
        pessoa_fisica__nome='reitor',
        pessoa_fisica__cpf=cpf_valido(900001),
        setor=setor_raiz_suap,
        funcao_atividade__codigo='0062',
        setor_funcao=setor_raiz_suap,
        setor_lotacao=setor_raiz_siape,
        setor_exercicio=setor_raiz_siape,
        _fill_optional=True,
        ativo=True,
    )
    baker.make(
        ServidorFuncaoHistorico,
        servidor=reitor,
        setor=setor_raiz_siape,
        setor_suap=setor_raiz_suap,
        atividade=reitor.funcao_atividade,
        data_inicio_funcao=_mock_now() - datetime.timedelta(days=1),
        data_fim_funcao=None,
    )

    request = rf.get('/')
    request.user = servidor_a.get_user()
    threadlocals.context.request = request
    threadlocals.context.user = servidor_a.get_user()

    vinculo = servidor_a.get_vinculo()
    papel_assinatura, _ = Papel.objects.get_or_create(
        vinculo=vinculo,
        data_inicio=datetime.date.today(),
        papel_content_type=ContentType.objects.get_for_model(servidor_a.cargo_emprego),
        papel_content_id=servidor_a.cargo_emprego_id,
        defaults={
            'tipo_papel': Papel.TIPO_PAPEL_CARGO,
            'descricao': 'Cargo de teste',
            'detalhamento': 'Cargo de teste',
            'portaria': '-',
            'setor_suap': setor_a0_suap,
        },
    )
    tipo_portaria = baker.make(docs.TipoDocumentoTexto, nome='portaria', sigla='port')

    return {
        'servidor_a': servidor_a,
        'setor_a0_suap': setor_a0_suap,
        'papel_assinatura': papel_assinatura,
        'tipo_portaria': tipo_portaria,
    }


@pytest.fixture
def criar_documento(dados_boletim):
    def _criar_documento():
        servidor_a = dados_boletim['servidor_a']
        setor_a0_suap = dados_boletim['setor_a0_suap']
        tipo_portaria = dados_boletim['tipo_portaria']
        papel_assinatura = dados_boletim['papel_assinatura']

        documento = baker.make(
            docs.DocumentoTexto,
            setor_dono=setor_a0_suap,
            modelo__tipo_documento_texto=tipo_portaria,
            nivel_acesso=docs.Documento.NIVEL_ACESSO_PUBLICO,
            usuario_criacao=servidor_a.get_user(),
            status=docs.DocumentoStatus.STATUS_CONCLUIDO,
            variaveis='',
        )
        assinatura = docs.Assinatura.objects.create(
            vinculo=servidor_a.get_vinculo(),
            cpf=servidor_a.get_vinculo().pessoa.get_cpf_ou_cnpj_ou_passaporte(),
            nome_papel=papel_assinatura.detalhamento,
            papel=papel_assinatura,
            hmac=f'test-{uuid.uuid4()}',
        )
        docs.AssinaturaDocumentoTexto.objects.create(documento=documento, assinatura=assinatura)
        documento.marcar_como_assinado()
        documento.finalizar_documento()
        documento.save()
        return documento

    return _criar_documento


@pytest.fixture
def criar_boletim_programado(dados_boletim):
    def _criar_boletim_programado(*, gerar_edicao_inicial=True):
        servidor_a = dados_boletim['servidor_a']
        setor_a0_suap = dados_boletim['setor_a0_suap']
        tipo_portaria = dados_boletim['tipo_portaria']

        boletim_programado = boletim_models.BoletimProgramado.objects.create(
            titulo='Boletim de serviço',
            nivel_acesso=[docs.Documento.NIVEL_ACESSO_PUBLICO],
            programado=True,
            criado_por=servidor_a.get_user(),
        )
        boletim_programado.tipo_documento.add(tipo_portaria)
        boletim_models.ConfiguracaoSetorBoletim.objects.create(
            boletim_programado=boletim_programado,
            descricao='Setor A0',
            setor_documento=setor_a0_suap,
        )
        if gerar_edicao_inicial:
            boletim_programado.gerar_boletim_diario(data=datetime.datetime(2018, 8, 13))
        return boletim_programado

    return _criar_boletim_programado
