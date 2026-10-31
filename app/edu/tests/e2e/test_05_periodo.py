"""Fluxo 006: executar o período letivo — aula, nota e entrega da etapa pelo professor.

Quinto elo, e o coração do módulo: é aqui que o diário deixa de ser cadastro e vira
histórico escolar. A ordem importa e é validada pelo próprio SUAP — a etapa recusa ser
entregue enquanto houver aluno sem nota, e depois de entregue o professor perde a posse
e só volta a mexer via solicitação de relançamento.

Este módulo faz pela interface exatamente o que o replay ORM da funcionalidade 005 faz,
com os mesmos valores (aula de 20/03/2019, nota 70, etapa 1 entregue). É de propósito:
a fixture ``seed_periodo_executado`` do módulo 06 é guardada por ``Aula.objects.exists()``
e vira no-op quando este módulo já rodou, então os dois caminhos precisam terminar no
mesmo estado.

O professor não tem ``edu.view_diario`` (ver ``edu/permissions.yaml``): a porta dele é
``/edu/meus_diarios/`` → ``/edu/meu_diario/<pk>/<etapa>/``, e não a tela de diário da
secretaria. As ações de aula/nota/etapa têm URL própria, que é o que este teste exercita.
"""

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import mensagem_de_erro, mensagem_de_sucesso
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '21/03/2019'
MATRICULA_ALUNO = '20191101010001'


@pytest.fixture
def diario_do_professor(edu_seed):
    """Diário POS.0001 da turma 2019.1 do curso 10101, com a etapa 1 em posse do professor.

    A devolução da posse (e a limpeza de aula/nota) é o que torna o módulo **re-executável**:
    entregar a etapa é irreversível pela interface do professor, e a suíte e2e não dá
    flush, então sem isto a segunda execução encontraria a etapa fechada e todo o fluxo
    responderia "A etapa precisa estar em posse do professor". É o equivalente ORM do
    "Reabrir Período" que o módulo 06 exercita pela interface.
    """
    from edu.models import Aula, Diario, MatriculaDiario, NotaAvaliacao, SolicitacaoRelancamentoEtapa

    # `ano_letivo` é parte da chave, não redundância: a cadeia vive em 2019 e o smoke de rota
    # cria turma/diários de sacrifício em outro ano no MESMO curso — e `replicar_diario`
    # multiplica cópias. Sem o filtro, este `.get()` estoura `MultipleObjectsReturned` na
    # segunda execução em `--reuse-db`. Mesma razão de `seed.diario_da_especializacao`.
    diario = Diario.objects.get(
        componente_curricular__componente__sigla='POS.0001',
        turma__curso_campus__codigo='10101',
        turma__periodo_letivo=1,
        turma__ano_letivo__ano=2019,
    )
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_PROFESSOR, situacao=Diario.SITUACAO_ABERTO)
    Aula.objects.filter(professor_diario__diario=diario, etapa=1).delete()
    NotaAvaliacao.objects.filter(matricula_diario__diario=diario, item_configuracao_avaliacao__configuracao_avaliacao__etapa=1).update(nota=None)
    # `situacao` volta a CURSANDO porque `pode_registrar_nota` só libera para aluno
    # cursando — depois que o módulo 06 fecha o período, o aluno fica aprovado/reprovado.
    MatriculaDiario.objects.filter(diario=diario).update(nota_1=None, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    # Solicitação pendente de relançamento bloqueia nova entrega ("encontra-se em
    # análise"), e o teste de relançamento deixa uma para trás.
    SolicitacaoRelancamentoEtapa.objects.filter(professor_diario__diario=diario).delete()
    diario.refresh_from_db()
    return diario


@pytest.fixture
def aula_registrada(diario_do_professor):
    """Uma aula na etapa 1 — sem aula o SUAP recusa a entrega da etapa.

    Criada por ORM porque quem cobre o cadastro de aula pela interface é
    ``test_professor_registra_aula``; aqui ela é só pré-condição.
    """
    from edu.models import Aula, ProfessorDiario

    professor_diario = ProfessorDiario.objects.get(diario=diario_do_professor, professor__vinculo__user__username='100007')
    return Aula.objects.create(
        etapa=1,
        quantidade=60,
        data='2019-03-20',
        conteudo='Apresentação da disciplina',
        professor_diario=professor_diario,
    )


@pytest.fixture
def plano_de_ensino(diario_do_professor):
    """Plano de ensino do diário POS.0001, com o ciclo de aprovação zerado.

    O plano nasce junto com o diário (``Diario.save`` o cria quando o curso exige plano de
    ensino) e o ciclo submissão→aprovação→homologação é irreversível pela interface — só há
    "devolver". Zerar as três datas por ORM é o que torna este módulo re-executável.
    """
    from edu.models import PlanoEnsino

    plano = diario_do_professor.planoensino_set.get()
    PlanoEnsino.objects.filter(pk=plano.pk).update(data_submissao=None, data_aprovacao=None, data_homologacao=None)
    plano.refresh_from_db()
    return plano


def test_professor_preenche_o_plano_de_ensino(logado_edu, plano_de_ensino):
    """O plano é o contrato pedagógico do diário: ementa, objetivos, metodologia, referências.

    ``PlanoEnsinoAdmin.has_change_permission`` só libera enquanto não houver homologação, e
    ``PlanoEnsino.can_change`` exige que quem edita seja professor do diário — é por isso que
    este teste é do professor e roda antes da submissão.
    """
    tela = Tela(logado_edu('professor')).ir(f'/admin/edu/planoensino/{plano_de_ensino.pk}/change/')
    tela.preencher_formulario(
        [
            ('Ementa', 'textarea', 'A origem e a formação da língua portuguesa.'),
            ('Justificativa', 'textarea', 'Análise dos efeitos das mudanças culturais na Educação.'),
            ('Objetivo Geral', 'textarea', 'A evolução fonológica, morfológica e sintática.'),
            ('Objetivos Específicos', 'textarea', 'A expansão da língua portuguesa.'),
            ('Conteúdo Programático', 'textarea', 'Estudo dos elementos das situações de ensino.'),
            ('Metodologia', 'textarea', 'Estudo dos objetivos educacionais.'),
            ('Informações Adicionais', 'textarea', 'Apresentação da disciplina'),
        ]
    )
    tela.preencher_linha(0, 'referencia', 'texto', '82192')
    # `input[name=_save]` e não "Salvar" por texto: nesta tela do admin convivem o submit e o
    # link "Salvar em PDF", e o `name` é o que identifica o salvamento sem ambiguidade.
    salvar = tela.pagina.locator('input[name=_save]')
    assert salvar.count(), f'a tela de plano de ensino não ofereceu o submit de salvar. URL: {tela.pagina.url}'
    salvar.first.click()
    tela.esperar()

    # Sem asserção de banner aqui: `PlanoEnsino.get_absolute_url` aponta para o PDF do plano,
    # e o admin do SUAP redireciona para lá depois de salvar — a resposta é um PDF, não uma
    # página com mensagem. O que prova o salvamento é o estado do plano.
    plano_de_ensino.refresh_from_db()
    assert plano_de_ensino.metodologia, 'a UI disse que salvou, mas o plano continua vazio'
    assert plano_de_ensino.referenciabibliograficabasica_set.exists(), 'referência bibliográfica não gravada'


def test_ciclo_de_aprovacao_do_plano_de_ensino(logado_edu, plano_de_ensino):
    """Professor submete → Coordenador de Curso aprova → Diretor Acadêmico homologa.

    Os três passos num teste só porque cada um é pré-condição do próximo e a interface não
    oferece atalho: as abas de ``PlanoEnsinoAdmin`` são filtradas por papel E por estado
    (``get_actions`` só publica a ação da aba certa para o grupo certo), então "aprovar" sem
    ter submetido não é um caminho que exista para clicar.
    """
    passos = [
        ('professor', 'tab_aguardando_minha_subissao', 'Submeter', 'Submissão realizada com sucesso.'),
        ('coordenador_curso', 'tab_aguardando_minha_aprovacao', 'Aprovar', 'Aprovação realizada com sucesso.'),
        ('diretor_academico', 'tab_aguardando_homologacao', 'Homologar', 'Homologação realizada com sucesso.'),
    ]
    for papel, aba, acao, mensagem in passos:
        tela = Tela(logado_edu(papel)).ir(f'/admin/edu/planoensino/?tab={aba}')
        tela.selecionar_item('POS.0001')
        tela.preencher('Ação', 'lista', acao)
        tela.clicar_acao('Aplicar')
        tela.sucesso(mensagem)

    plano_de_ensino.refresh_from_db()
    assert plano_de_ensino.data_submissao, 'submissão não registrada'
    assert plano_de_ensino.data_aprovacao, 'aprovação do coordenador não registrada'
    assert plano_de_ensino.data_homologacao, 'homologação do diretor acadêmico não registrada'


def test_plano_homologado_aparece_na_consulta_publica(new_context, plano_de_ensino):
    """Plano homologado é documento público: a tela anônima do SUAP o lista.

    A homologação vem por ORM porque o caminho de interface dela é
    ``test_ciclo_de_aprovacao_do_plano_de_ensino``; aqui o que se verifica é o filtro
    público e o recorte ``data_homologacao__isnull=False`` de ``PlanoEnsinoPublicForm``.
    """
    from datetime import date

    from edu.models import PlanoEnsino

    PlanoEnsino.objects.filter(pk=plano_de_ensino.pk).update(data_homologacao=date(2019, 3, 21))
    tela = Tela(new_context().new_page()).ir('/edu/planoensino_public/')
    tela.preencher('Ano Letivo', 'lista', '2019')
    tela.preencher('Período Letivo', 'lista', '1')
    tela.clicar_botao('Filtrar')

    tela.ver_texto('POS.0001')


def test_professor_configura_forma_de_avaliacao(logado_edu, diario_do_professor):
    """O professor customiza as avaliações da etapa (tipo, sigla, descrição, data).

    É o que define quantas notas a etapa cobra — e, por consequência, o que a entrega da
    etapa vai exigir. O item criado aqui é removido no fim: ele gera ``NotaAvaliacao`` para
    todo aluno do diário, e uma nota a mais mudaria o que ``test_entrega_da_etapa...`` cobra.
    """
    configuracao = diario_do_professor.configuracao_avaliacao_1()
    item = configuracao.itemconfiguracaoavaliacao_set.first()
    assert item is not None, 'a configuração de avaliação nasce com um item; sem ele não há o que editar'
    original = (item.sigla, item.descricao)
    try:
        tela = Tela(logado_edu('professor')).ir(f'/admin/edu/configuracaoavaliacao/{configuracao.pk}/change/')
        tela.preencher_linha(0, 'sigla', 'texto', 'S1')
        tela.preencher_linha(0, 'descricao', 'texto', 'Avaliação final')
        tela.preencher_linha(0, 'data', 'data', '20/07/2019')
        tela.clicar_botao('Salvar')

        tela.sucesso('Atualização realizada com sucesso.')
        item.refresh_from_db()
        assert item.sigla == 'S1', 'a UI disse que salvou, mas a avaliação não mudou'
    finally:
        # Devolve sigla e descrição: os testes de nota deste módulo endereçam a avaliação
        # por queryset, mas o boletim do módulo 08 mostra a sigla.
        type(item).objects.filter(pk=item.pk).update(sigla=original[0], descricao=original[1])


def test_professor_lanca_faltas(logado_edu, diario_do_professor, aula_registrada):
    """A chamada é lançada por aula: cada campo é ``<matrícula no diário>;<aula>``.

    O SUAP limita a falta à quantidade de aulas do dia, então o valor lançado aqui (1) tem de
    ser ≤ 60. Sem aula cadastrada a aba nem renderiza campo — daí o ``aula_registrada``.
    """
    from edu.models import Falta, MatriculaDiario

    matricula_diario = MatriculaDiario.objects.filter(diario=diario_do_professor, situacao=MatriculaDiario.SITUACAO_CURSANDO).first()
    assert matricula_diario is not None, 'diário sem aluno cursando: nada a chamar'
    faltas = Falta.objects.filter(matricula_diario=matricula_diario, aula=aula_registrada)
    try:
        tela = Tela(logado_edu('professor')).ir(f'/edu/meu_diario/{diario_do_professor.pk}/1/?tab=faltas')
        # A aba precisa oferecer o campo do par aluno-aula — é ele que dispara o AJAX.
        campo = tela.pagina.locator(f'input[name="{matricula_diario.pk};{aula_registrada.pk}"]')
        expect(campo).to_be_visible()

        # Cada campo grava por AJAX no `change` (o submit "Salvar alterações" só recarrega a
        # tela); o endpoint é o mesmo que a interface chama.
        resposta = tela.pagina.goto(f'/edu/registrar_chamada_ajax/{matricula_diario.pk}/{aula_registrada.pk}/1/')
        assert resposta.status == 200, 'o endpoint de chamada recusou o lançamento'
        assert faltas.filter(quantidade=1).exists(), 'falta não persistida'
    finally:
        faltas.delete()


def test_secretario_defere_relancamento_de_etapa(logado_edu, relogio, diario_do_professor, aula_registrada):
    """A secretaria é quem devolve a posse da etapa ao professor, deferindo a solicitação.

    A solicitação é criada por ORM (o caminho de interface dela é
    ``test_professor_solicita_relancamento_da_etapa``); o que se cobre aqui é o outro lado:
    a tela de Solicitações de Usuários e o efeito do deferimento, que é a posse voltar.
    """
    from edu.models import ProfessorDiario, SolicitacaoRelancamentoEtapa

    professor_diario = ProfessorDiario.objects.get(diario=diario_do_professor, professor__vinculo__user__username='100007')
    diario_do_professor.entregar_etapa(1)
    solicitacao = SolicitacaoRelancamentoEtapa.objects.create(professor_diario=professor_diario, etapa=1, motivo='Faltou lançar a nota do aluno')

    relogio.congelar('20/07/2019')
    tela = Tela(logado_edu('secretario')).ir(f'/edu/solicitacaousuario/{solicitacao.pk}/')
    tela.clicar_botao('Deferir')

    tela.sucesso('Solicitação deferida com sucesso.')
    diario_do_professor.refresh_from_db()
    assert not diario_do_professor.em_posse_do_registro(1), 'solicitação deferida mas a posse não voltou ao professor'


def test_professor_ve_o_diario_em_meus_diarios(logado_edu, diario_do_professor):
    """A porta de entrada do professor: filtro por período e acesso ao diário."""
    page = logado_edu('professor')
    page.goto('/edu/meus_diarios/')
    page.select_option('select[name=ano-periodo]', label='2019.1')

    link = page.get_by_role('link', name=f'{diario_do_professor.pk} - POS.0001')
    expect(link.first).to_be_visible()
    link.first.click()
    expect(page.get_by_role('heading', name='POS.0001')).to_be_visible()


def test_professor_registra_aula(logado_edu, diario_do_professor):
    """A aula é o que contabiliza carga horária cumprida e habilita o lançamento de falta."""
    from edu.models import Aula

    page = logado_edu('professor')
    page.goto(f'/edu/adicionar_aula_diario/{diario_do_professor.pk}/1/')
    expect(page.get_by_role('heading', name='Adicionar Aula')).to_be_visible()

    page.fill('input[name=quantidade]', '60')
    page.select_option('select[name=etapa]', label='Primeira')
    page.fill('input[name=data]', '2019-03-20')
    page.fill('textarea[name=conteudo]', 'Apresentação da disciplina')
    page.click('input[type=submit]')

    mensagem_de_sucesso(page, 'Aula cadastrada/atualizada com sucesso.')
    assert Aula.objects.filter(professor_diario__diario=diario_do_professor, etapa=1).exists(), 'a UI disse que salvou, mas a aula não persistiu'


def test_entrega_da_etapa_exige_nota_lancada(logado_edu, relogio, diario_do_professor, aula_registrada):
    """Sem nota o SUAP barra a entrega; com a nota lançada, a etapa fecha.

    Os dois caminhos no mesmo teste porque são o mesmo fato de negócio visto dos dois
    lados, e porque o caminho de erro só é observável ANTES de a nota existir — separá-los
    criaria dependência de ordem entre testes.
    """
    from edu.models import MatriculaDiario, NotaAvaliacao

    avaliacoes = NotaAvaliacao.objects.filter(
        matricula_diario__diario=diario_do_professor,
        matricula_diario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
        item_configuracao_avaliacao__configuracao_avaliacao__etapa=1,
    )
    nota_avaliacao = avaliacoes.filter(matricula_diario__matricula_periodo__aluno__matricula=MATRICULA_ALUNO).first()
    assert nota_avaliacao is not None, 'o diário não gerou avaliação para o aluno: turma/matrícula fora do lugar'

    # A entrega da etapa só é aceita dentro da janela do calendário acadêmico (a etapa 1
    # vai até 18/07/2019); 21/03 é cedo demais para fechar.
    relogio.congelar('20/07/2019')
    page = logado_edu('professor')

    if nota_avaliacao.nota is None:
        page.goto(f'/edu/entregar_etapa/{diario_do_professor.pk}/1/')
        page.click('input[type=submit]')
        mensagem_de_erro(page, 'A etapa só pode ser entregue quando todas as notas forem lançadas.')

    # Lançamento de nota é AJAX por avaliação — é assim que a planilha de notas grava.
    # Precisa cobrir TODOS os alunos cursando: a etapa só fecha sem nota faltante.
    for avaliacao in avaliacoes:
        resposta = page.goto(f'/edu/registrar_nota_ajax/{avaliacao.pk}/70/')
        assert resposta.status == 200, 'o endpoint de lançamento de nota recusou a requisição'
    nota_avaliacao.refresh_from_db()
    assert nota_avaliacao.nota == 70, 'nota não gravada'

    page.goto(f'/edu/entregar_etapa/{diario_do_professor.pk}/1/')
    page.click('input[type=submit]')
    mensagem_de_sucesso(page, 'Etapa entregue com sucesso.')

    # `refresh_from_db` não é detalhe: sem ele o objeto em memória continua com a posse
    # antiga e a asserção passa sem medir nada.
    diario_do_professor.refresh_from_db()
    assert diario_do_professor.em_posse_do_registro(1), 'etapa entregue mas a posse não passou para o registro escolar'
    matricula_diario = MatriculaDiario.objects.get(pk=nota_avaliacao.matricula_diario_id)
    assert matricula_diario.nota_1 is not None, 'a nota da etapa não foi consolidada na matrícula do diário'


def test_professor_solicita_relancamento_da_etapa(logado_edu, relogio, diario_do_professor, aula_registrada):
    """Depois de entregue, mexer na etapa exige pedir o relançamento à secretaria."""
    from edu.models import ProfessorDiario, SolicitacaoRelancamentoEtapa

    professor_diario = ProfessorDiario.objects.get(diario=diario_do_professor, professor__vinculo__user__username='100007')
    # Pré-condição montada por ORM: a `diario_do_professor` devolve a posse ao professor
    # para o módulo ser re-executável, e sem etapa entregue não existe relançamento a pedir.
    diario_do_professor.entregar_etapa(1)

    relogio.congelar('20/07/2019')
    page = logado_edu('professor')
    page.goto(f'/edu/solicitar_relancamento_etapa/{professor_diario.pk}/1/')
    page.fill('textarea[name=motivo]', 'Faltou lançar a nota do aluno')
    page.click('input[type=submit]')

    mensagem_de_sucesso(page, 'Solicitação enviada com sucesso.')
    assert SolicitacaoRelancamentoEtapa.objects.filter(professor_diario=professor_diario, etapa=1).exists(), (
        'solicitação de relançamento não registrada'
    )


def test_entrega_da_etapa_sem_nota_exige_confirmacao(logado_edu, relogio, diario_do_professor, aula_registrada):
    """Depois do fim da etapa final, o professor pode entregar com aluno sem nota — confirmando.

    É a válvula de escape do fechamento: ``Diario.pode_ser_entregue_sem_nota`` só libera depois
    de a etapa final ter vencido, e aí a tela passa a oferecer o "Confirmar entrega sem nota".
    Sem essa confirmação a entrega continua sendo recusada, que é o caminho coberto por
    ``test_entrega_da_etapa_exige_nota_lancada``.
    """
    from edu.models import ComponenteCurricular

    # Duas pré-condições, as duas de ``Diario.pode_ser_entregue_sem_nota``: a data tem de ser
    # posterior ao fim da etapa final (20/07 aqui, o diário termina em 19/07) e o componente
    # curricular tem de admitir fechamento com pendência — que é o campo que a coordenação
    # marca justamente para permitir isto.
    componente_curricular = diario_do_professor.componente_curricular
    ComponenteCurricular.objects.filter(pk=componente_curricular.pk).update(pode_fechar_pendencia=True)
    try:
        relogio.congelar('20/07/2019')
        tela = Tela(logado_edu('professor')).ir(f'/edu/entregar_etapa/{diario_do_professor.pk}/1/')
        tela.preencher('Confirmar entrega sem nota', 'checkbox', 'marcar')
        tela.clicar_botao('Confirmar Entrega')

        tela.sucesso('Etapa entregue com sucesso.')
        diario_do_professor.refresh_from_db()
        assert diario_do_professor.em_posse_do_registro(1), 'etapa entregue sem nota, mas a posse não passou para o registro'
    finally:
        ComponenteCurricular.objects.filter(pk=componente_curricular.pk).update(pode_fechar_pendencia=False)
