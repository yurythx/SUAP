"""Factories dos models de ``projetos`` (Extensão), compartilhadas pelas suítes do módulo.

Nasceram com a suíte e2e (``projetos/tests/e2e/``), que monta cada estado do ciclo de vida do
edital e do projeto direto no seed, sem encadear pela interface. Factory cria linha: regra de
negócio (classificar, avaliar, concluir) continua nos métodos de model e nas telas.

Models de outros apps vêm das factories do app dono (``rh.tests.factories``,
``comum.tests.factories``) — não duplique aqui.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from projetos.models import (
    AreaLicaoAprendida,
    AreaTematica,
    Avaliacao,
    AvaliacaoAluno,
    AvaliadorIndicado,
    CaracterizacaoBeneficiario,
    ColaboradorVoluntario,
    ComissaoEdital,
    Comunicador,
    CriterioAvaliacao,
    CriterioAvaliacaoAluno,
    CriterioPreSelecao,
    Desembolso,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    EditalArquivo,
    Etapa,
    ExtratoMensalProjeto,
    FocoTecnologico,
    FotoNEPP,
    FotoProjeto,
    HistoricoAlteracaoPeriodoProjeto,
    HistoricoEquipe,
    HistoricoInteresseCusteioProjeto,
    HistoricoOrientacaoProjeto,
    ItemAvaliacao,
    ItemAvaliacaoAluno,
    ItemMemoriaCalculo,
    LicaoAprendida,
    MembroNEPP,
    Meta,
    NucleoExtensao,
    ObjetivoVisitaTecnica,
    OcorrenciaProjeto,
    OfertaProjeto,
    OfertaProjetoPorGrupo,
    OfertaProjetoPorTema,
    Participacao,
    PreSelecao,
    Projeto,
    ProjetoAnexo,
    ProjetoCancelado,
    Recurso,
    RecursoProjeto,
    RegistroConclusaoProjeto,
    RegistroExecucaoEtapa,
    RegistroFrequencia,
    RegistroGasto,
    Tema,
    TermoParceriaAdesao,
    TipoBeneficiario,
    TipoVinculo,
    VisitaTecnica,
)
from comum.tests.factories import AnoFactory, PrestadorServicoFactory
from financeiro.models import NaturezaDespesa
from rh.tests.factories import SetorFactory, TitulacaoFactory, UnidadeOrganizacionalFactory


def _daqui_a(dias: int) -> datetime.datetime:
    return datetime.datetime.now() + datetime.timedelta(days=dias)


class EditalFactory(DjangoModelFactory):
    """Edital de extensão de fomento interno, por campus, em período de inscrição.

    As datas default são relativas a agora (inscrição aberta); quem precisa de outra fase passa
    as seis datas (ver ``janela`` em ``projetos/tests/e2e/conftest.py``).
    """

    class Meta:
        model = Edital

    titulo = factory.Sequence(lambda n: f'Edital de Extensão {n}')
    descricao = 'Edital de extensão criado por factory.'
    tipo_edital = Edital.EXTENSAO
    tipo_fomento = Edital.FOMENTO_INTERNO
    forma_selecao = Edital.CAMPUS
    inicio_inscricoes = factory.LazyFunction(lambda: _daqui_a(-1))
    fim_inscricoes = factory.LazyFunction(lambda: _daqui_a(5))
    inicio_pre_selecao = factory.LazyFunction(lambda: _daqui_a(10))
    inicio_selecao = factory.LazyFunction(lambda: _daqui_a(15))
    fim_selecao = factory.LazyFunction(lambda: _daqui_a(20))
    divulgacao_selecao = factory.LazyFunction(lambda: _daqui_a(21))
    autorizado = True
    autorizado_em = factory.LazyFunction(datetime.datetime.now)


class OfertaProjetoFactory(DjangoModelFactory):
    class Meta:
        model = OfertaProjeto

    edital = factory.SubFactory(EditalFactory)
    uo = factory.LazyFunction(lambda: SetorFactory().uo)
    qtd_aprovados = 5
    qtd_selecionados = 3


class EditalAnexoAuxiliarFactory(DjangoModelFactory):
    """Anexo do edital (documento que acompanha o edital, ex.: formulários)."""

    class Meta:
        model = EditalAnexoAuxiliar

    edital = factory.SubFactory(EditalFactory)
    nome = factory.Sequence(lambda n: f'Anexo do edital {n}')
    descricao = 'Anexo auxiliar'
    ordem = 1


class EditalAnexoFactory(DjangoModelFactory):
    """Anexo exigido dos membros dos projetos (termo de compromisso, por exemplo)."""

    class Meta:
        model = EditalAnexo

    edital = factory.SubFactory(EditalFactory)
    nome = factory.Sequence(lambda n: f'Anexo dos projetos {n}')
    descricao = 'Termo de compromisso'
    tipo_membro = EditalAnexo.COORDENADOR_TECNICO_ADMINISTRATIVO
    vinculo = TipoVinculo.VOLUNTARIO
    ordem = 1


class CriterioAvaliacaoFactory(DjangoModelFactory):
    class Meta:
        model = CriterioAvaliacao

    edital = factory.SubFactory(EditalFactory)
    descricao = 'Adequação da proposta'
    pontuacao_maxima = Decimal('10')
    ordem_desempate = 1


class ProjetoFactory(DjangoModelFactory):
    """Projeto em edição (sem data de envio). Os campos de estado vêm por parâmetro."""

    class Meta:
        model = Projeto

    edital = factory.SubFactory(EditalFactory)
    uo = factory.LazyFunction(lambda: SetorFactory().uo)
    titulo = factory.Sequence(lambda n: f'Projeto de Extensão {n}')
    justificativa = 'Justificativa do projeto'
    resumo = 'Resumo do projeto'
    objetivo_geral = 'Objetivo geral do projeto'
    metodologia = 'Metodologia do projeto'
    acompanhamento_e_avaliacao = 'Acompanhamento do projeto'
    resultados_esperados = 'Disseminação dos resultados'
    inicio_execucao = factory.LazyFunction(lambda: _daqui_a(30).date())
    fim_execucao = factory.LazyFunction(lambda: _daqui_a(395).date())


class ParticipacaoFactory(DjangoModelFactory):
    """Membro da equipe. ``responsavel=True`` torna o vínculo o coordenador do projeto (``Participacao.save``)."""

    class Meta:
        model = Participacao

    projeto = factory.SubFactory(ProjetoFactory)
    vinculo = TipoVinculo.VOLUNTARIO
    carga_horaria = 4


class ProjetoAnexoFactory(DjangoModelFactory):
    """Anexo pendente (sem arquivo) de um membro — o que ``upload_anexo`` preenche."""

    class Meta:
        model = ProjetoAnexo

    projeto = factory.SubFactory(ProjetoFactory)


class AvaliacaoFactory(DjangoModelFactory):
    """Avaliação gravada sem passar pelo ``save`` do model.

    ``Avaliacao.save(self)`` não aceita argumentos (o ``create`` do factory_boy passa
    ``force_insert``) e, pior para teste, recalcula a pontuação e **reclassifica** o edital a cada
    gravação — o que apagaria o estado que um teste de classificação quer observar. Por isso
    ``bulk_create``: quem precisa da pontuação a grava no projeto.
    """

    class Meta:
        model = Avaliacao

    projeto = factory.SubFactory(ProjetoFactory)
    parecer = 'Favorável'
    pontuacao = Decimal('0')

    @classmethod
    def _create(cls, model_class: type[Avaliacao], *args: object, **kwargs: object) -> Avaliacao:
        return model_class.objects.bulk_create([model_class(**kwargs)])[0]


class ItemAvaliacaoFactory(DjangoModelFactory):
    """Nota de um critério numa avaliação — é o que impede o critério de ser removido."""

    class Meta:
        model = ItemAvaliacao

    avaliacao = factory.SubFactory(AvaliacaoFactory)
    criterio_avaliacao = factory.SubFactory(CriterioAvaliacaoFactory)
    pontuacao = Decimal('5')


class TemaFactory(DjangoModelFactory):
    """Tema de uma área temática (as áreas vêm do ``initial_data``; os temas, não)."""

    class Meta:
        model = Tema
        django_get_or_create = ('descricao',)

    descricao = factory.Sequence(lambda n: f'Tema de extensão {n}')
    areatematica = factory.LazyFunction(lambda: AreaTematica.objects.get(descricao='Cultura'))


class OfertaProjetoPorGrupoFactory(DjangoModelFactory):
    class Meta:
        model = OfertaProjetoPorGrupo

    edital = factory.SubFactory(EditalFactory)
    grupo = factory.Sequence(lambda n: f'Grupo {n}')
    pre_selecionados = 2
    selecionados = 1


class OfertaProjetoPorTemaFactory(DjangoModelFactory):
    """Vagas de uma área temática (``tema`` nulo = a área inteira)."""

    class Meta:
        model = OfertaProjetoPorTema

    edital = factory.SubFactory(EditalFactory)
    area_tematica = factory.LazyFunction(lambda: AreaTematica.objects.get(descricao='Cultura'))
    selecionados = 1


class RecursoFactory(DjangoModelFactory):
    """Fonte de recurso do edital. ``despesa`` (``financeiro.NaturezaDespesa``) é obrigatória: não há factory dela."""

    class Meta:
        model = Recurso

    edital = factory.SubFactory(EditalFactory)
    origem = 'PROEX'
    valor = Decimal('1000')


class FocoTecnologicoFactory(DjangoModelFactory):
    """Foco tecnológico; ``campi`` é o que o formulário do projeto encadeia ao campus escolhido."""

    class Meta:
        model = FocoTecnologico
        django_get_or_create = ('descricao',)
        skip_postgeneration_save = True  # `campi.add` grava a M2M; re-salvar o foco não muda nada

    descricao = factory.Sequence(lambda n: f'Foco tecnológico {n}')

    @factory.post_generation
    def campi(self, create: bool, extracted: list | None, **kwargs: object) -> None:
        if create and extracted:
            self.campi.add(*extracted)


class MetaFactory(DjangoModelFactory):
    class Meta:
        model = Meta

    projeto = factory.SubFactory(ProjetoFactory)
    ordem = 1
    descricao = factory.Sequence(lambda n: f'Meta {n}')


class EtapaFactory(DjangoModelFactory):
    """Atividade de uma meta, dentro do período de execução do projeto. ``responsavel`` (uma ``Participacao``) é obrigatório."""

    class Meta:
        model = Etapa

    meta = factory.SubFactory(MetaFactory)
    ordem = 1
    descricao = factory.Sequence(lambda n: f'Atividade {n}')
    unidade_medida = 'Unidade'
    qtd = 1
    indicadores_qualitativos = 'Verificação de qualidade'
    inicio_execucao = factory.LazyAttribute(lambda etapa: etapa.meta.projeto.inicio_execucao)
    fim_execucao = factory.LazyAttribute(lambda etapa: etapa.meta.projeto.inicio_execucao + datetime.timedelta(days=30))
    forma_comprovacao = 'Relatório'


class CaracterizacaoBeneficiarioFactory(DjangoModelFactory):
    """Público-alvo previsto. Os tipos de beneficiário vêm do ``initial_data`` do módulo."""

    class Meta:
        model = CaracterizacaoBeneficiario

    projeto = factory.SubFactory(ProjetoFactory)
    tipo_beneficiario = factory.LazyFunction(lambda: TipoBeneficiario.objects.get(descricao='Público Interno do Instituto'))
    quantidade = 10


class ItemMemoriaCalculoFactory(DjangoModelFactory):
    """Item do plano de aplicação na natureza 339018 (``financeiro`` não tem factory: quem usa semeia a natureza)."""

    class Meta:
        model = ItemMemoriaCalculo

    projeto = factory.SubFactory(ProjetoFactory)
    despesa = factory.LazyFunction(lambda: NaturezaDespesa.objects.get(codigo='339018'))
    origem = 'PROEX'
    descricao = factory.Sequence(lambda n: f'Memória de cálculo {n}')
    unidade_medida = 'Unidade'
    qtd = 1
    valor_unitario = Decimal('1000')


class DesembolsoFactory(DjangoModelFactory):
    """Desembolso de um item da memória de cálculo (a despesa vem do item, no ``save`` do model).

    ``Desembolso.save(self)`` não aceita argumentos, e o ``create`` do factory_boy passa
    ``force_insert``: por isso o ``_create`` chama o ``save`` sem nada.
    """

    class Meta:
        model = Desembolso

    item = factory.SubFactory(ItemMemoriaCalculoFactory)
    projeto = factory.LazyAttribute(lambda desembolso: desembolso.item.projeto)
    ano = factory.LazyFunction(lambda: AnoFactory(ano=datetime.date.today().year))
    mes = 1
    valor = Decimal('1000')

    @classmethod
    def _create(cls, model_class: type[Desembolso], *args: object, **kwargs: object) -> Desembolso:
        desembolso = model_class(**kwargs)
        desembolso.save()
        return desembolso


class CriterioPreSelecaoFactory(DjangoModelFactory):
    """Critério da ficha de pré-seleção. Com um no edital, "Pré-selecionar" vira "Pré-avaliar" (a ficha)."""

    class Meta:
        model = CriterioPreSelecao

    edital = factory.SubFactory(EditalFactory)
    descricao = factory.Sequence(lambda n: f'Critério de pré-seleção {n}')


class PreSelecaoFactory(DjangoModelFactory):
    """Ficha de pré-seleção preenchida. ``projeto`` é ``PROTECT``: quem cria apaga antes do projeto."""

    class Meta:
        model = PreSelecao

    projeto = factory.SubFactory(ProjetoFactory)
    parecer = 'Parecer da pré-seleção'


class ComissaoEditalFactory(DjangoModelFactory):
    """Comissão de avaliação: com ``Edital.exige_comissao`` (default), só os membros podem ser indicados."""

    class Meta:
        model = ComissaoEdital
        skip_postgeneration_save = True  # `vinculos_membros.add` grava a M2M

    edital = factory.SubFactory(EditalFactory)

    @factory.post_generation
    def vinculos_membros(self, create: bool, extracted: list | None, **kwargs: object) -> None:
        if create and extracted:
            self.vinculos_membros.add(*extracted)


class AvaliadorIndicadoFactory(DjangoModelFactory):
    """Indicação de um avaliador (``vinculo``) para o projeto, recém-convidada e sem resposta."""

    class Meta:
        model = AvaliadorIndicado

    projeto = factory.SubFactory(ProjetoFactory)
    convidado_em = factory.LazyFunction(datetime.datetime.now)


class RecursoProjetoFactory(DjangoModelFactory):
    """Recurso do coordenador contra o resultado do edital ("Interpor Recurso" → "Do Edital"), ainda sem avaliação."""

    class Meta:
        model = RecursoProjeto

    projeto = factory.SubFactory(ProjetoFactory)
    justificativa = factory.Sequence(lambda n: f'Justificativa do recurso {n}')
    data_solicitacao = factory.LazyFunction(datetime.datetime.now)


# ------------------------------------------------------------ execução do projeto


def _salvar_sem_argumentos(model_class: type, kwargs: dict) -> object:
    """``create`` para os models cujo ``save(self)`` não aceita argumentos (o do factory_boy passa ``force_insert``)."""
    objeto = model_class(**kwargs)
    objeto.save()
    return objeto


class RegistroExecucaoEtapaFactory(DjangoModelFactory):
    """Execução registrada de uma atividade, ainda sem avaliação do monitor (``dt_avaliacao`` nulo)."""

    class Meta:
        model = RegistroExecucaoEtapa

    etapa = factory.SubFactory(EtapaFactory)
    tipo_indicador_qualitativo = RegistroExecucaoEtapa.ATENDIDO
    qtd = 1
    inicio_execucao = factory.LazyAttribute(lambda registro: registro.etapa.inicio_execucao)
    fim_execucao = factory.LazyAttribute(lambda registro: registro.etapa.fim_execucao)
    info_ind_qualitativo = 'Resultado dos indicadores'
    obs = factory.Sequence(lambda n: f'Execução registrada {n}')
    data_cadastro_execucao = factory.LazyFunction(datetime.date.today)


class RegistroGastoFactory(DjangoModelFactory):
    """Gasto registrado contra um desembolso (ano, mês e item vêm dele), ainda sem avaliação.

    ``RegistroGasto.save(self)`` não aceita argumentos e copia o ``item`` do desembolso.
    """

    class Meta:
        model = RegistroGasto

    desembolso = factory.SubFactory(DesembolsoFactory)
    ano = factory.LazyAttribute(lambda registro: registro.desembolso.ano)
    mes = factory.LazyAttribute(lambda registro: registro.desembolso.mes)
    descricao = factory.Sequence(lambda n: f'Gasto registrado {n}')
    qtd = 1
    valor_unitario = Decimal('100')
    data_cadastro = factory.LazyFunction(datetime.date.today)

    @classmethod
    def _create(cls, model_class: type[RegistroGasto], *args: object, **kwargs: object) -> RegistroGasto:
        return _salvar_sem_argumentos(model_class, kwargs)


class RegistroFrequenciaFactory(DjangoModelFactory):
    """Frequência/atividade diária de um membro, aguardando a validação do coordenador. Passe ``cadastrada_por``."""

    class Meta:
        model = RegistroFrequencia

    projeto = factory.SubFactory(ProjetoFactory)
    descricao = factory.Sequence(lambda n: f'Atividade diária {n}')
    data = factory.LazyFunction(datetime.date.today)
    carga_horaria = 4
    cadastrada_em = factory.LazyFunction(datetime.datetime.now)


class LicaoAprendidaFactory(DjangoModelFactory):
    """Lição aprendida; as áreas vêm do ``initial_data`` do módulo."""

    class Meta:
        model = LicaoAprendida

    projeto = factory.SubFactory(ProjetoFactory)
    area_licao_aprendida = factory.LazyFunction(lambda: AreaLicaoAprendida.objects.get(descricao='GERENCIAMENTO DO TEMPO'))
    descricao = factory.Sequence(lambda n: f'Lição aprendida {n}')


class OcorrenciaProjetoFactory(DjangoModelFactory):
    """Ocorrência registrada no projeto. Passe ``cadastrada_por``: só o autor edita ou exclui."""

    class Meta:
        model = OcorrenciaProjeto

    projeto = factory.SubFactory(ProjetoFactory)
    ocorrencia = factory.Sequence(lambda n: f'<p>Ocorrência {n}</p>')


class ExtratoMensalProjetoFactory(DjangoModelFactory):
    """Extrato mensal do cartão pesquisador. O arquivo é só o nome: ninguém o abre nos testes."""

    class Meta:
        model = ExtratoMensalProjeto

    projeto = factory.SubFactory(ProjetoFactory)
    ano = factory.LazyFunction(lambda: AnoFactory(ano=datetime.date.today().year))
    mes = 1
    arquivo = 'upload/projetos/extratos_mensais/extrato-e2e.pdf'


class TermoParceriaAdesaoFactory(DjangoModelFactory):
    """Comprovante de parceria/adesão. O arquivo é só o nome: ninguém o abre nos testes."""

    class Meta:
        model = TermoParceriaAdesao

    projeto = factory.SubFactory(ProjetoFactory)
    descricao = factory.Sequence(lambda n: f'Comprovante de parceria {n}')
    arquivo = 'projetos/termos_parcerias/termo-e2e.pdf'


class FotoProjetoFactory(DjangoModelFactory):
    """Foto do projeto. Com a imagem inexistente no storage, o ``save`` não abre o PIL para redimensionar."""

    class Meta:
        model = FotoProjeto

    projeto = factory.SubFactory(ProjetoFactory)
    legenda = factory.Sequence(lambda n: f'Foto {n}')
    imagem = 'upload/projetos/fotos/foto-e2e.png'

    @classmethod
    def _create(cls, model_class: type[FotoProjeto], *args: object, **kwargs: object) -> FotoProjeto:
        return _salvar_sem_argumentos(model_class, kwargs)


class ObjetivoVisitaTecnicaFactory(DjangoModelFactory):
    class Meta:
        model = ObjetivoVisitaTecnica
        django_get_or_create = ('descricao',)

    descricao = factory.Sequence(lambda n: f'Objetivo de visita {n}')


class VisitaTecnicaFactory(DjangoModelFactory):
    """Visita técnica de um campus (informe ``campus``) a uma instituição; ``objetivos`` é a M2M."""

    class Meta:
        model = VisitaTecnica
        skip_postgeneration_save = True  # `objetivos.add` grava a M2M

    data = factory.LazyFunction(datetime.date.today)
    instituicao_visitada = factory.Sequence(lambda n: f'Instituição visitada {n}')
    encaminhamentos = 'Encaminhamentos da visita'
    nome_contato = 'Contato da instituição'
    telefone_contato = '(84) 3333-4444'
    email_contato = 'contato@instituicao.example'

    @factory.post_generation
    def objetivos(self, create: bool, extracted: list | None, **kwargs: object) -> None:
        if create and extracted:
            self.objetivos.add(*extracted)


# ------------------------------------------------------------------ equipe do projeto


class HistoricoEquipeFactory(DjangoModelFactory):
    """Entrada de um membro na equipe (o que ``adicionar_registro_historico_equipe`` grava).

    A ``ParticipacaoFactory`` NÃO cria histórico: certificado, declarações e a inativação leem
    daqui as datas de entrada e saída. Por padrão, "servidor inserido" no início da execução.
    """

    class Meta:
        model = HistoricoEquipe

    participante = factory.SubFactory(ParticipacaoFactory)
    projeto = factory.LazyAttribute(lambda historico: historico.participante.projeto)
    data_movimentacao = factory.LazyAttribute(lambda historico: historico.participante.projeto.inicio_execucao)
    tipo_de_evento = HistoricoEquipe.EVENTO_ADICIONAR_SERVIDOR
    categoria = factory.LazyAttribute(lambda h: HistoricoEquipe.COORDENADOR if h.participante.responsavel else HistoricoEquipe.MEMBRO)
    vinculo = factory.LazyAttribute(lambda historico: historico.participante.vinculo)
    carga_horaria = factory.LazyAttribute(lambda historico: historico.participante.carga_horaria)


class ColaboradorVoluntarioFactory(DjangoModelFactory):
    """Colaborador externo (um ``PrestadorServico`` cadastrado pelo Coordenador de Extensão)."""

    class Meta:
        model = ColaboradorVoluntario

    nome = factory.Sequence(lambda n: f'Colaborador Externo {n}')
    prestador = factory.SubFactory(PrestadorServicoFactory)
    email = factory.Sequence(lambda n: f'colaborador{n}@externo.example')
    titulacao = factory.SubFactory(TitulacaoFactory)


class CriterioAvaliacaoAlunoFactory(DjangoModelFactory):
    """Critério do formulário de avaliação do aluno (cadastro do gerente; vale para todos os editais)."""

    class Meta:
        model = CriterioAvaliacaoAluno
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Critério de avaliação do aluno {n}')
    descricao_criterio = 'Assiduidade e pontualidade nas atividades'


class AvaliacaoAlunoFactory(DjangoModelFactory):
    """Avaliação parcial do aluno pelo coordenador, ainda sem as considerações do aluno."""

    class Meta:
        model = AvaliacaoAluno

    participacao = factory.SubFactory(ParticipacaoFactory)
    tipo_avaliacao = AvaliacaoAluno.PARCIAL
    data_avaliacao = factory.LazyFunction(datetime.datetime.now)
    consideracoes_coordenador = factory.Sequence(lambda n: f'Considerações do coordenador {n}')


class ItemAvaliacaoAlunoFactory(DjangoModelFactory):
    class Meta:
        model = ItemAvaliacaoAluno

    avaliacao = factory.SubFactory(AvaliacaoAlunoFactory)
    criterio = factory.SubFactory(CriterioAvaliacaoAlunoFactory)
    pontuacao = ItemAvaliacaoAluno.BOM


class HistoricoOrientacaoProjetoFactory(DjangoModelFactory):
    """Orientação de um aluno (``orientado``) por um servidor da equipe (``orientador``), em aberto."""

    class Meta:
        model = HistoricoOrientacaoProjeto

    orientado = factory.SubFactory(ParticipacaoFactory)
    orientador = factory.SubFactory(ParticipacaoFactory)
    projeto = factory.LazyAttribute(lambda orientacao: orientacao.orientado.projeto)
    data_inicio = factory.LazyAttribute(lambda orientacao: orientacao.orientado.projeto.inicio_execucao)


class RegistroConclusaoProjetoFactory(DjangoModelFactory):
    """Relatório de conclusão já avaliado e aprovado pelo monitor — com ele, ``Projeto.get_status`` é "Concluído"."""

    class Meta:
        model = RegistroConclusaoProjeto

    projeto = factory.SubFactory(ProjetoFactory)
    resultados_alcancados = 'Resultados alcançados pelo projeto'
    disseminacao_resultados = 'Seminário de encerramento'
    dt_avaliacao = factory.LazyFunction(datetime.date.today)
    aprovado = True


# ------------------------------------------------- conclusão e ciclo de vida do projeto


class ProjetoCanceladoFactory(DjangoModelFactory):
    """Pedido de cancelamento do coordenador, aguardando o parecer (``data_avaliacao`` nulo)."""

    class Meta:
        model = ProjetoCancelado

    projeto = factory.SubFactory(ProjetoFactory)
    justificativa_cancelamento = factory.Sequence(lambda n: f'Justificativa do cancelamento {n}')
    data_solicitacao = factory.LazyFunction(datetime.datetime.now)


class HistoricoAlteracaoPeriodoProjetoFactory(DjangoModelFactory):
    """Pedido de alteração do período de execução (o novo período começa 10 dias depois), aguardando avaliação."""

    class Meta:
        model = HistoricoAlteracaoPeriodoProjeto

    projeto = factory.SubFactory(ProjetoFactory)
    inicio_execucao = factory.LazyAttribute(lambda pedido: pedido.projeto.inicio_execucao)
    fim_execucao = factory.LazyAttribute(lambda pedido: pedido.projeto.fim_execucao)
    novo_inicio_execucao = factory.LazyAttribute(lambda pedido: pedido.projeto.inicio_execucao + datetime.timedelta(days=10))
    novo_fim_execucao = factory.LazyAttribute(lambda pedido: pedido.projeto.fim_execucao + datetime.timedelta(days=10))
    justificativa = factory.Sequence(lambda n: f'Atraso na entrega dos materiais {n}')


class HistoricoInteresseCusteioProjetoFactory(DjangoModelFactory):
    """Pedido do coordenador para passar a ter interesse no custeio (cartão pesquisador). Passe ``cadastrado_por``."""

    class Meta:
        model = HistoricoInteresseCusteioProjeto

    projeto = factory.SubFactory(ProjetoFactory)
    tinha_interesse = False
    tem_interesse = True
    justificativa = factory.Sequence(lambda n: f'O projeto passou a ter despesas de custeio {n}')


class EditalArquivoFactory(DjangoModelFactory):
    """Retificação do edital (arquivo enviado depois da publicação). O arquivo é só o nome: ninguém o abre."""

    class Meta:
        model = EditalArquivo

    edital = factory.SubFactory(EditalFactory)
    arquivo = 'upload/projetos/edital/retificacao-e2e.pdf'
    data_cadastro = factory.LazyFunction(datetime.datetime.now)


class NucleoExtensaoFactory(DjangoModelFactory):
    """Núcleo de Extensão e Prática Profissional (NEPP). Passe ``uo`` e ``coordenador`` (um ``Vinculo``)."""

    class Meta:
        model = NucleoExtensao

    nome = factory.Sequence(lambda n: f'NEPP {n}')
    area_atuacao = 'Agroecologia'
    descricao_atividades = 'Oficinas com agricultores familiares'


class MembroNEPPFactory(DjangoModelFactory):
    class Meta:
        model = MembroNEPP

    nepp = factory.SubFactory(NucleoExtensaoFactory)


class FotoNEPPFactory(DjangoModelFactory):
    """Foto do NEPP. A imagem é só o nome: ninguém a abre."""

    class Meta:
        model = FotoNEPP

    nepp = factory.SubFactory(NucleoExtensaoFactory)
    descricao = factory.Sequence(lambda n: f'Foto do núcleo {n}')
    imagem = 'upload/projetos/nepp/fotos/foto-e2e.png'


class ComunicadorFactory(DjangoModelFactory):
    """Mensagem já enviada pelo comunicador da Extensão. Passe ``cadastrado_por``."""

    class Meta:
        model = Comunicador

    titulo = factory.Sequence(lambda n: f'Mensagem {n}')
    conteudo = '<p>Conteúdo da mensagem</p>'
    destinatarios = 'Coordenadores de extensão'
