# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``rh``.

Reutilizáveis por testes de qualquer app (o dono do modelo provê a factory).

Cobrem o substrato de pessoal (``Setor``, ``PessoaFisica``, ``Servidor`` — o ``User`` e o
``Vinculo`` nascem do ``Servidor.save``), substituindo o fixture legado ``suap_data``, e a
**cadeia de função/chefia**. As factories de ``ServidorFuncaoHistorico`` recebem
``servidor``/``setor``/``setor_suap`` por parâmetro.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import factory
from django.contrib.contenttypes.models import ContentType
from factory.django import DjangoModelFactory

from djtools.utils import get_datetime_now
from rh.models import (
    AfastamentoSiape,
    ArquivoUnico,
    CargoEmprego,
    Funcao,
    GrupoCargoEmprego,
    JornadaTrabalho,
    Papel,
    PessoaFisica,
    PessoaJuridica,
    Servidor,
    ServidorAfastamento,
    ServidorFuncaoHistorico,
    Setor,
    Situacao,
    TipoUnidadeOrganizacional,
    Titulacao,
    UnidadeOrganizacional,
)


def _hoje() -> date:
    return get_datetime_now().date()


def cnpj_valido(n: int) -> str:
    """CNPJ formatado e com dígitos verificadores corretos, derivado de ``n`` (único por ``n``)."""
    base = [int(d) for d in f'{n % 10**8:08d}'] + [0, 0, 0, 1]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        resto = sum(d * peso for d, peso in zip(base, pesos, strict=True)) % 11
        base.append(0 if resto < 2 else 11 - resto)
    c = ''.join(map(str, base))
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}'


def cpf_valido(n: int) -> str:
    """CPF formatado e com dígitos verificadores corretos, derivado de ``n`` (único por ``n``)."""
    digitos = [int(d) for d in f'{n % 10**9:09d}']
    for tamanho in (9, 10):
        soma = sum(d * peso for d, peso in zip(digitos, range(tamanho + 1, 1, -1), strict=True))
        digitos.append(0 if soma % 11 < 2 else 11 - soma % 11)
    c = ''.join(map(str, digitos))
    return f'{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}'


class SetorFactory(DjangoModelFactory):
    """Setor da árvore SUAP (``codigo`` nulo), sempre com campus (``uo``).

    A ``uo`` é herdada do ``superior``; sem superior com campus, o próprio setor vira campus
    (ganha uma ``UnidadeOrganizacional``). Precisa ter: o middleware desloga servidor cujo
    setor SUAP não tem campus. ``SetorFactory(campus=False)`` pula a criação.
    """

    class Meta:
        model = Setor
        skip_postgeneration_save = True

    sigla = factory.Sequence(lambda n: f'ST{n}')
    nome = factory.LazyAttribute(lambda o: f'Setor {o.sigla}')
    codigo = None

    @factory.post_generation
    def campus(obj: Setor, create: bool, extracted: bool | None, **kwargs: object) -> None:
        if not create or extracted is False or obj.codigo or obj.uo_id:
            return
        # UnidadeOrganizacional.save regrava todos os setores: é o que preenche obj.uo no banco.
        UnidadeOrganizacionalFactory(setor=obj, sigla=obj.sigla, nome=obj.nome)
        obj.refresh_from_db()


class SetorSiapeFactory(SetorFactory):
    """Setor da árvore SIAPE (``codigo`` preenchido), p.ex. o ``setor`` de uma função. Sem campus."""

    codigo = factory.Sequence(lambda n: f'S{n:06d}')


class TipoUnidadeOrganizacionalFactory(DjangoModelFactory):
    """Tipo da UO, por id — as constantes ``UnidadeOrganizacional.TIPO_*`` são os ids."""

    class Meta:
        model = TipoUnidadeOrganizacional
        django_get_or_create = ('id',)

    id = UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO
    descricao = 'Campus'


class UnidadeOrganizacionalFactory(DjangoModelFactory):
    """Campus SUAP. Informe ``setor``; a factory não o cria (o ``SetorFactory`` cria a UO).

    O ``tipo`` tem default porque ``UnidadeOrganizacional.objects.uo()`` — a consulta
    canônica de "isto é um campus" — filtra justamente por ele. Sem tipo, a UO existe mas
    não é campus para ninguém: o form de edital do ``remanejamento`` a recusava e o
    ``get_campi_user`` do ``projetos_ensino`` devolvia lista vazia.
    """

    class Meta:
        model = UnidadeOrganizacional

    nome = factory.Sequence(lambda n: f'Campus {n}')
    sigla = factory.Sequence(lambda n: f'CP{n}')
    codigo_protocolo = factory.Sequence(lambda n: f'{n % 100000:05d}')
    tipo = factory.SubFactory(TipoUnidadeOrganizacionalFactory)


class SituacaoFactory(DjangoModelFactory):
    class Meta:
        model = Situacao
        django_get_or_create = ('codigo',)

    codigo = Situacao.ATIVO_PERMANENTE
    nome_siape = 'ATIVO PERMANENTE'
    excluido = False


class JornadaTrabalhoFactory(DjangoModelFactory):
    class Meta:
        model = JornadaTrabalho
        django_get_or_create = ('codigo',)

    codigo = '01'
    nome = '40h'
    excluido = False


class GrupoCargoEmpregoFactory(DjangoModelFactory):
    class Meta:
        model = GrupoCargoEmprego
        django_get_or_create = ('codigo',)

    codigo = '01'
    nome = 'Grupo X'
    sigla = 'X'
    categoria = 'tecnico_administrativo'
    excluido = False


class CargoEmpregoFactory(DjangoModelFactory):
    class Meta:
        model = CargoEmprego
        django_get_or_create = ('codigo',)

    codigo = '01'
    nome = 'Cargo A'
    grupo_cargo_emprego = factory.SubFactory(GrupoCargoEmpregoFactory)
    sigla_escolaridade = '01'
    excluido = False


class PessoaJuridicaFactory(DjangoModelFactory):
    """Fornecedor. O CNPJ é validado no `save`, então vem do gerador com dígitos corretos."""

    class Meta:
        model = PessoaJuridica
        django_get_or_create = ('cnpj',)

    cnpj = factory.Sequence(cnpj_valido)
    nome = factory.Sequence(lambda n: f'Pessoa Jurídica {n}')


class PessoaFisicaFactory(DjangoModelFactory):
    class Meta:
        model = PessoaFisica

    nome = factory.Sequence(lambda n: f'Pessoa {n}')
    cpf = factory.Sequence(lambda n: cpf_valido(n + 1))


class ServidorFactory(DjangoModelFactory):
    """Servidor ativo, técnico-administrativo, lotado num ``SetorFactory``.

    O ``save`` cria o ``User`` (``username`` = matrícula) e o ``Vinculo``: use
    ``servidor.get_user()`` / ``servidor.get_vinculo()``. O ``save`` busca grupos por nome
    (``Servidor``, ``Chefe de Setor``...): o teste precisa da fixture ``sync_permissions``.
    Custo medido: ~140 ms e ~220 queries por servidor. Sem ``setor_exercicio`` por padrão:
    informá-lo liga a checagem de campus SUAP x SIAPE do ``save``, que zera ``setor`` quando a
    ``uo`` do setor SIAPE não é equivalente à do SUAP.
    """

    class Meta:
        model = Servidor
        django_get_or_create = ('matricula',)

    matricula = factory.Sequence(lambda n: f'{9000000 + n}')
    pessoa_fisica = factory.SubFactory(PessoaFisicaFactory)
    ativo = True
    situacao = factory.SubFactory(SituacaoFactory)
    cargo_emprego = factory.SubFactory(CargoEmpregoFactory)
    jornada_trabalho = factory.SubFactory(JornadaTrabalhoFactory)
    setor = factory.SubFactory(SetorFactory)

    @classmethod
    def _generate(cls, strategy: str, params: dict) -> Servidor:
        """Devolve o servidor da matrícula antes de avaliar as declarações, quando ele já existe.

        O ``django_get_or_create`` sozinho só consulta o banco DEPOIS de gerar a ``SubFactory``:
        cada reuso criava uma ``PessoaFisica`` órfã — e, com ``pessoa_fisica__cpf`` fixo, um CPF
        duplicado. Como no get-or-create, os demais campos de quem já existe não são aplicados.
        """
        if strategy == factory.CREATE_STRATEGY and 'matricula' in params:
            existente = Servidor.objects.filter(matricula=params['matricula']).first()
            if existente is not None:
                return existente
        return super()._generate(strategy, params)


class FuncaoFactory(DjangoModelFactory):
    class Meta:
        model = Funcao
        django_get_or_create = ('codigo',)

    codigo = factory.Sequence(lambda n: f'F{n:03d}')
    nome = factory.Sequence(lambda n: f'Função {n}')


class FuncaoChefiaFactory(FuncaoFactory):
    """Função com código fixo de chefia (``CD``).

    O ``save`` de ``Funcao`` força ``eh_funcao_chefia=True`` para os códigos fixos
    e limpa o cache de códigos de chefia — sem dependência de estado entre testes.
    """

    codigo = Funcao.CODIGO_CD
    nome = 'Chefe de Setor'


class ServidorFuncaoHistoricoFactory(DjangoModelFactory):
    """Histórico de função ativo (sem fim).

    Informe ``servidor`` (rh.Servidor), ``setor`` (SIAPE) e, para chefia,
    ``setor_suap`` — todos informados pelo teste.
    """

    class Meta:
        model = ServidorFuncaoHistorico

    funcao = factory.SubFactory(FuncaoFactory)
    data_inicio_funcao = factory.LazyFunction(lambda: _hoje() - timedelta(days=30))
    data_fim_funcao = None


class ServidorFuncaoChefiaFactory(ServidorFuncaoHistoricoFactory):
    """Histórico de função de **chefia** ativo: torna ``servidor`` chefe de ``setor_suap``.

    Informe ``servidor``, ``setor`` (SIAPE) e ``setor_suap``.
    """

    funcao = factory.SubFactory(FuncaoChefiaFactory)


class AfastamentoSiapeFactory(DjangoModelFactory):
    """Tipo de afastamento do catálogo do SIAPE (ex.: licença capacitação)."""

    class Meta:
        model = AfastamentoSiape
        django_get_or_create = ('codigo',)

    codigo = factory.Sequence(lambda n: f'{n:04d}')
    sigla = factory.Sequence(lambda n: f'AF{n}')
    nome = factory.Sequence(lambda n: f'Afastamento SIAPE {n}')
    tipo = AfastamentoSiape.OUTROS


class ServidorAfastamentoFactory(DjangoModelFactory):
    """Afastamento concedido a um servidor.

    ``servidor`` é informado pelo teste, assim como as datas, vindas do
    chamador. ``data_inicio`` e ``afastamento`` são ``editable=False``, então o
    factory_boy os define na construção, não por atribuição posterior.
    """

    class Meta:
        model = ServidorAfastamento

    # servidor / data_inicio / data_termino: informados pelo chamador.
    afastamento = factory.SubFactory(AfastamentoSiapeFactory)
    cancelado = False


class TitulacaoFactory(DjangoModelFactory):
    class Meta:
        model = Titulacao
        django_get_or_create = ('codigo',)

    codigo = '26'
    nome = 'Doutor'
    titulo_masculino = 'Dr.'
    titulo_feminino = 'Dra.'


class PapelFactory(DjangoModelFactory):
    """Papel de cargo ativo (desde 2000) do ``servidor`` — o que o ``PapelForm`` oferece para assinar."""

    class Meta:
        model = Papel
        exclude = ('servidor',)

    servidor = factory.SubFactory(ServidorFactory)
    vinculo = factory.LazyAttribute(lambda o: o.servidor.get_vinculo())
    descricao = factory.LazyAttribute(lambda o: str(o.servidor.cargo_emprego))
    detalhamento = factory.LazyAttribute(lambda o: str(o.servidor.cargo_emprego))
    portaria = '000'
    data_inicio = date(2000, 1, 1)
    papel_content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(CargoEmprego))
    papel_content_id = factory.LazyAttribute(lambda o: o.servidor.cargo_emprego_id)


class ArquivoUnicoFactory(DjangoModelFactory):
    """Arquivo PDF mínimo gravado no storage; hashes únicos por sequência."""

    class Meta:
        model = ArquivoUnico

    conteudo = factory.django.FileField(filename='AU.pdf', data=b'%PDF-1.4 conteudo')
    tipo_conteudo = 'application/pdf'
    tamanho_em_bytes = 17
    nome_original_primeiro_upload = 'documento.pdf'
    data_hora_primeiro_upload = factory.LazyFunction(get_datetime_now)
    data_hora_criacao_registro = factory.LazyFunction(get_datetime_now)
    hash_sha512 = factory.Sequence(lambda n: f'a{n:0127d}')
    hash_sha512_link_id = factory.Sequence(lambda n: f'b{n:0127d}')


class AcaoSaudeFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.AcaoSaude'

    descricao = factory.LazyFunction(lambda: f'Ação E2E {uuid4().hex[:12]}')
    data_inicio = factory.LazyFunction(lambda: _hoje() + timedelta(days=1))
    data_fim = factory.LazyFunction(lambda: _hoje() + timedelta(days=30))
    periodo_inscricao_inicio = factory.LazyFunction(lambda: _hoje() - timedelta(days=1))
    periodo_inscricao_fim = factory.LazyFunction(lambda: _hoje() + timedelta(days=30))
    dias_semanas = '0,1,2,3,4,5,6'


class CargaHorariaReduzidaFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.CargaHorariaReduzida'

    servidor = factory.SubFactory(ServidorFactory)
    tipo = 1
    status = 1
    ano = factory.LazyFunction(lambda: _hoje().year)
    data_inicio = factory.LazyFunction(lambda: _hoje() + timedelta(days=1))
    data_termino = factory.LazyFunction(lambda: _hoje() + timedelta(days=30))
    nova_jornada = '30 HORAS SEMANAIS'


class DocumentacaoExigidaFactory(DjangoModelFactory):
    """Documento anexado ao processo de carga horária; ``diretorio`` é o caminho do arquivo no storage."""

    class Meta:
        model = 'rh.DocumentacaoExigida'

    processo = factory.SubFactory(CargaHorariaReduzidaFactory)
    nome = 'documento.pdf'
    diretorio = factory.Sequence(lambda n: f'cargahoraria/documento-{n}.pdf')
    tamanho = 1


class ImportacaoSiapeFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.ImportacaoSiape'

    arquivo = factory.LazyFunction(lambda: f'e2e-{uuid4().hex}.zip')
    origem = 'tela'
    pasta = ''


class ImportacaoSiapeArquivoFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.ImportacaoSiapeArquivo'

    importacao = factory.SubFactory(ImportacaoSiapeFactory)
    nome_ref = 'bancos.REF'
    nome_txt = 'bancos.TXT'
    layout = 'bancos'
    selecionado = True


class ImportacaoSiapeOcorrenciaFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.ImportacaoSiapeOcorrencia'

    arquivo = factory.SubFactory(ImportacaoSiapeArquivoFactory)
    nivel = 'warning'
    linha = 1
    mensagem = factory.LazyFunction(lambda: f'Aviso E2E {uuid4().hex}')


class BancoFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.Banco'
        django_get_or_create = ('codigo',)

    codigo = '001'
    sigla = 'BB'
    nome = 'Banco do Brasil'


class AvaliadorFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.Avaliador'
        django_get_or_create = ('vinculo',)

    matricula_siape = factory.Sequence(lambda n: str(8900000 + n))


class SolicitacaoAlteracaoFotoFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.SolicitacaoAlteracaoFoto'

    foto = factory.django.ImageField(width=150, height=200)
    solicitante = factory.SubFactory(ServidorFactory)


class ViagemFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.Viagem'

    servidor = factory.SubFactory(ServidorFactory)
    vinculo = factory.LazyAttribute(lambda o: o.servidor.get_vinculo())
    codigo_siorg = 'E2ERH'
    nome_siorg = 'Campus RH E2E'
    nome_proposto = factory.LazyAttribute(lambda o: o.servidor.nome)
    tipo_proposto = 'Servidor'
    numero_pcdp = factory.LazyFunction(lambda: uuid4().hex)
    objetivo_viagem = 'Capacitação RH E2E'
    data_inicio_viagem = factory.LazyFunction(lambda: _hoje() + timedelta(days=1))
    data_fim_viagem = factory.LazyFunction(lambda: _hoje() + timedelta(days=2))
    situacao = 6


class AlertaGestaoPessoaFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.AlertaGestaoPessoa'

    tipo_acao = 4
    data_acao = factory.LazyFunction(get_datetime_now)
    registro_afetado = factory.LazyFunction(lambda: f'Alerta E2E {uuid4().hex}')


def _hora(hora: int) -> object:
    from datetime import time

    return time(hora)


class AgendaAtendimentoHorarioFactory(DjangoModelFactory):
    """Horário de atendimento de uma ação de saúde; ``profissional`` (rh.Servidor) vem do chamador."""

    class Meta:
        model = 'rh.AgendaAtendimentoHorario'

    acao_saude = factory.SubFactory(AcaoSaudeFactory)
    hora_inicio = factory.LazyFunction(lambda: _hora(8))
    hora_fim = factory.LazyFunction(lambda: _hora(9))
    quantidade_vaga = 1


class HorarioAgendadoFactory(DjangoModelFactory):
    """Agendamento para amanhã; ``solicitante`` (comum.Vinculo) vem do chamador."""

    class Meta:
        model = 'rh.HorarioAgendado'

    horario = factory.SubFactory(AgendaAtendimentoHorarioFactory)
    data_consulta = factory.LazyFunction(lambda: _hoje() + timedelta(days=1))


class SetorJornadaHistoricoFactory(DjangoModelFactory):
    """Jornada vigente de um setor; ``setor`` vem do chamador."""

    class Meta:
        model = 'rh.SetorJornadaHistorico'

    jornada_trabalho = factory.SubFactory(JornadaTrabalhoFactory)
    data_inicio_da_jornada = factory.LazyFunction(_hoje)


class CronogramaFolhaFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.CronogramaFolha'

    mes = factory.LazyFunction(lambda: _hoje().month)
    # Por caminho: `comum.tests.factories` importa este módulo no topo, e o import direto fecharia o ciclo.
    ano = factory.SubFactory('comum.tests.factories.AnoFactory')
    data_abertura_atualizacao_folha = factory.LazyFunction(_hoje)
    data_fechamento_processamento_folha = factory.LazyFunction(lambda: _hoje() + timedelta(days=10))
    data_consulta_previa_folha = factory.LazyFunction(lambda: _hoje() + timedelta(days=15))
    data_abertura_proxima_folha = factory.LazyFunction(lambda: _hoje() + timedelta(days=30))


class ServidorSetorLotacaoHistoricoFactory(DjangoModelFactory):
    """Lotação SIAPE do servidor; ``servidor`` e os setores vêm do chamador."""

    class Meta:
        model = 'rh.ServidorSetorLotacaoHistorico'

    data_inicio_setor_lotacao = factory.LazyFunction(_hoje)
    hora_atualizacao_siape = factory.LazyFunction(get_datetime_now)


class HorarioSemanalFactory(DjangoModelFactory):
    """Horário de 30h semanais (6h por dia) cobrindo o período do processo de carga horária."""

    class Meta:
        model = 'rh.HorarioSemanal'

    processo_reducao_ch = factory.SubFactory(CargaHorariaReduzidaFactory)
    data_inicio = factory.LazyAttribute(lambda o: o.processo_reducao_ch.data_inicio)
    data_fim = factory.LazyAttribute(lambda o: o.processo_reducao_ch.data_termino)
    seg = 6
    ter = 6
    qua = 6
    qui = 6
    sex = 6
    jornada_semanal = '30.0'


class IndicadoresPublicosFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.IndicadoresPublicos'

    titulo = factory.LazyFunction(lambda: f'Indicador E2E {uuid4().hex[:12]}')
    render_to = factory.LazyFunction(lambda: f'grafico_{uuid4().hex[:8]}')


class AfastamentoSiapeEfetivoExercicioFactory(DjangoModelFactory):
    """Regra de efetivo exercício; ``afastamentos`` (lista de AfastamentoSiape) por post-generation."""

    class Meta:
        model = 'rh.AfastamentoSiapeEfetivoExercicio'
        skip_postgeneration_save = True

    dias_efetivo_exercicio = 30

    @factory.post_generation
    def afastamentos(obj: object, create: bool, extracted: list | None, **kwargs: object) -> None:
        if create and extracted:
            obj.afastamentos.set(extracted)


class SubgrupoOcorrenciaFactory(DjangoModelFactory):
    """Subgrupo de ocorrência (só do SUAP). Sem chave única: reaproveita o primeiro de mesma descrição."""

    class Meta:
        model = 'rh.SubgrupoOcorrencia'

    descricao = 'EXCLUSAO'

    @classmethod
    def _create(cls, model_class: type, *args: object, **kwargs: object) -> object:
        return model_class.objects.filter(descricao=kwargs['descricao']).first() or super()._create(model_class, *args, **kwargs)


class GrupoOcorrenciaFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.GrupoOcorrencia'
        django_get_or_create = ('codigo',)

    codigo = 'E2E'
    nome = 'Grupo de Ocorrência E2E'


class OcorrenciaFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.Ocorrencia'
        django_get_or_create = ('codigo',)

    codigo = factory.Sequence(lambda n: f'E{n % 10000:04d}')
    nome = factory.Sequence(lambda n: f'Ocorrência E2E {n}')
    grupo_ocorrencia = factory.SubFactory(GrupoOcorrenciaFactory)


class ServidorOcorrenciaFactory(DjangoModelFactory):
    """Ocorrência de **exclusão** do servidor (há 30 dias): a que a reativação permanente remove.

    ``servidor`` vem do chamador.
    """

    class Meta:
        model = 'rh.ServidorOcorrencia'

    ocorrencia = factory.SubFactory(OcorrenciaFactory)
    subgrupo = factory.SubFactory(SubgrupoOcorrenciaFactory)
    diploma_legal_num = '000'
    data = factory.LazyFunction(lambda: _hoje() - timedelta(days=30))


class CargoClasseFactory(DjangoModelFactory):
    class Meta:
        model = 'rh.CargoClasse'
        django_get_or_create = ('codigo',)

    codigo = factory.LazyFunction(lambda: uuid4().hex[:10])
    nome = factory.LazyFunction(lambda: f'Classe E2E {uuid4().hex[:8]}')


class QuantitativoCargoClassePorCampusFactory(DjangoModelFactory):
    """Vagas de uma classe de cargo num campus; ``uo`` vem do chamador."""

    class Meta:
        model = 'rh.QuantitativoCargoClassePorCampus'

    cargo_classe = factory.SubFactory(CargoClasseFactory)
    quantidade = 7


class AreaVinculacaoFactory(DjangoModelFactory):
    """Área de vinculação de setores. O ``save`` do model não aceita argumentos: ``create`` não serve."""

    class Meta:
        model = 'rh.AreaVinculacao'

    descricao = factory.LazyFunction(lambda: f'Área E2E {uuid4().hex[:10]}')
    ordem = 1

    @classmethod
    def _create(cls, model_class: type, *args: object, **kwargs: object) -> object:
        area = model_class(**kwargs)
        area.save()
        return area


class PadraoVencimentoFactory(DjangoModelFactory):
    """Padrão de vencimento (catálogo ``unique_together`` de 190 combinações): reaproveita o existente."""

    class Meta:
        model = 'rh.PadraoVencimento'
        django_get_or_create = ('categoria', 'classe', 'posicao_vertical')

    categoria = 'docente'
    classe = 'E'
    posicao_vertical = '19'
