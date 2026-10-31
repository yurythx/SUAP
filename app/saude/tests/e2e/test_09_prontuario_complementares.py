"""Fluxos complementares do prontuário: encaminhamento, anotação, cartão SUS, pessoa externa.

Estes são os registros que não pertencem a um atendimento clínico — encaminhamento e anotação
interdisciplinar vivem no prontuário, o cartão SUS e a pessoa externa são dados cadastrais do
paciente, e a lista de alunos é o relatório de alergias que sai desses registros. As três abas
complementares da avaliação biomédica (informação adicional, saúde mental e nutrição) e as
transições de situação do atendimento (cancelar, reabrir) fecham o ciclo.

Os rótulos de Nutrição e Alimentação são as perguntas gravadas no modelo (com pontuação e grafia
próprias), não prosa do teste.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Atendimento, Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PRONTUARIO = '/saude/prontuario/{}/'
PRONTUARIOS = '/saude/prontuarios/'
ATENDIMENTO_MEDICO = '/saude/atendimento_medico_enfermagem/{}/'
FECHAR_ATENDIMENTO = '/saude/fechar_atendimento/{}/'
CANCELAR_ATENDIMENTO = '/saude/cancelar_atendimento/{}/'
REABRIR_ATENDIMENTO = '/saude/reabrir_atendimento/{}/'
ADICIONAR_ENCAMINHAMENTO = '/saude/adicionar_encaminhamento/{}/'
FINALIZAR_ENCAMINHAMENTO = '/saude/finalizar_encaminhamento/{}/'
ADICIONAR_ANOTACAO = '/saude/adicionar_anotacao_interdisciplinar/{}/'
ANOTACOES_PENDENTES = '/saude/anotacoes_pendentes/'
CONFIRMAR_LEITURA = '/saude/confirmar_leitura_anotacao/{}/'
AVALIACAO_BIOMEDICA = '/saude/avaliacao_biomedica/{}/'
ADICIONAR_INFORMACAO = '/saude/adicionar_informacao_adicional/{}/'
ADICIONAR_SAUDEMENTAL = '/saude/adicionar_saudemental/{}/'
ADICIONAR_NUTRICAO = '/saude/adicionar_nutricao_alimentacao/{}/'
ADICIONAR_HIPOTESE = '/saude/adicionar_hipotese_diagnostica/{}/'
EDITAR_HIPOTESE = '/saude/editar_hipotese_diagnostica/{}/'
ADICIONAR_CONDUTA = '/saude/adicionar_conduta_medica/{}/'
EDITAR_CONDUTA = '/saude/editar_conduta_medica/{}/'
ADICIONAR_ANAMNESE = '/saude/adicionar_anamnese/{}/'
ENVIAR_MENSAGEM = '/saude/enviar_mensagem_aluno/{}/{}/'
EDITAR_CARTAO_SUS = '/saude/editar_cartao_sus/{}/'
CADASTRAR_PESSOA_EXTERNA = '/saude/cadastrar_pessoa_externa/'
LISTA_ALUNOS = '/saude/lista_alunos/'

CPF_PESSOA_EXTERNA = '529.982.247-25'  # CPF válido fixo; a pessoa é criada uma vez por banco


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _ultimo_atendimento(tipo: int) -> Atendimento:
    """O atendimento mais recente do paciente para o tipo informado."""
    from saude.models import Atendimento

    atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=tipo).order_by('-id').first()
    assert atendimento is not None, f'atendimento do tipo {tipo} não foi criado pela tela'
    return atendimento


def _abrir_atendimento_medico(tela: Tela, vinculo_id: int) -> Atendimento:
    """Abre um atendimento médico/enfermagem novo pelo prontuário e devolve o registro."""
    from saude.models import TipoAtendimento

    tela.ir(PRONTUARIO.format(vinculo_id)).ver_titulo('Prontuário')
    tela.clicar_botao('Atendimento Médico/Enfermagem')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/atendimento_medico_enfermagem/\d+/$'))
    tela.esperar().sucesso('Atendimento Médico/Enfermagem gerado com sucesso.')
    return _ultimo_atendimento(TipoAtendimento.ENFERMAGEM_MEDICO)


def test_encaminhamento_e_anotacao_interdisciplinar(logado_saude: Callable[[str], Page]) -> None:
    """O médico encaminha e finaliza; o coordenador anota para o médico, que confirma a leitura."""
    medico = Tela(logado_saude('medico'))

    from saude.models import AnotacaoInterdisciplinar, EncaminhamentoPaciente, InteressadoAnotacaoInterdisciplinar

    _aluno, prontuario = _aluno_e_prontuario()
    vinculo = prontuario.vinculo

    # O encaminhamento é oferecido apenas a profissional de saúde, e é o tipo interno que
    # depois oferece o botão "Finalizar".
    medico.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Encaminhamentos')
    medico.aba('Encaminhamentos').clicar_botao('Adicionar')
    expect(medico.pagina).to_have_url(re.compile(rf'{ADICIONAR_ENCAMINHAMENTO.format(prontuario.pk)}$'))
    medico.preencher_formulario([('Tipo do Encaminhamento', 'Lista', 'Interno'), ('Descrição', 'TextArea', 'Encaminhamento E2E')])
    medico.clicar_botao('Salvar').sucesso('Encaminhamento registrado com sucesso.')
    encaminhamento = EncaminhamentoPaciente.objects.get(prontuario=prontuario, descricao='Encaminhamento E2E')
    assert encaminhamento.atendido_em is None, 'o encaminhamento recém-criado não pode estar finalizado'

    medico.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Encaminhamentos')
    medico.aba('Encaminhamentos').linha('Encaminhamento E2E').clicar_botao('Finalizar')
    expect(medico.pagina).to_have_url(re.compile(rf'{FINALIZAR_ENCAMINHAMENTO.format(encaminhamento.pk)}$'))
    medico.preencher('Observações', 'TextArea', 'Encaminhamento finalizado E2E')
    medico.clicar_botao('Salvar').sucesso('Encaminhamento finalizado com sucesso.')
    encaminhamento.refresh_from_db()
    assert encaminhamento.atendido_em is not None, 'a UI disse que finalizou, mas o encaminhamento continua pendente'
    assert encaminhamento.obs == 'Encaminhamento finalizado E2E', 'a observação da finalização não persistiu'

    # Anotação interdisciplinar com o médico como interessado: o autor é o coordenador, quem
    # confirma a leitura é o interessado, na tela de anotações pendentes.
    coordenador = Tela(logado_saude('coordenador_sistemico'))
    coordenador.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Anotações Interdisciplinares')
    coordenador.aba('Anotações Interdisciplinares').clicar_botao('Adicionar Anotação')
    expect(coordenador.pagina).to_have_url(re.compile(rf'{ADICIONAR_ANOTACAO.format(prontuario.pk)}$'))
    coordenador.preencher_formulario([('Anotação', 'TextArea', 'Anotação interdisciplinar E2E'), ('Interessados', 'Autocomplete Multiplo', '111002')])
    coordenador.clicar_botao('Enviar').sucesso('Anotação registrada com sucesso.')
    anotacao = AnotacaoInterdisciplinar.objects.get(prontuario=prontuario, anotacao='Anotação interdisciplinar E2E')
    interessado = InteressadoAnotacaoInterdisciplinar.objects.get(anotacao_interdisciplinar=anotacao)
    assert '111002' in str(interessado.interessado), 'o interessado indicado na tela não foi gravado'
    assert interessado.lido_em is None, 'a anotação recém-criada não pode estar lida'

    medico.ir(ANOTACOES_PENDENTES).ver_titulo('Anotações interdisciplinares pendentes de confirmação de leitura').ver_texto(
        'Anotação interdisciplinar E2E'
    )
    medico.linha('Anotação interdisciplinar E2E').clicar_botao('Confirmar leitura')
    medico.sucesso('Confirmação de leitura realizada com sucesso.')
    interessado.refresh_from_db()
    assert interessado.lido_em is not None, 'a UI disse que confirmou, mas a leitura continua pendente'


def test_abas_complementares_da_avaliacao_biomedica(logado_saude: Callable[[str], Page]) -> None:
    """O médico preenche Informação Adicional, Saúde Mental e Nutrição e Alimentação."""
    tela = Tela(logado_saude('medico'))

    from saude.models import InformacaoAdicional, NutricaoAlimentacao, SaudeMental, TipoAtendimento

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(PRONTUARIO.format(vinculo.pk)).ver_titulo('Prontuário')
    # O rótulo inteiro do botão: com só "Avaliação de Saúde", o `clicar_botao` (que prioriza link de
    # texto exato) às vezes resolvia um link para /saude/relatorio_avaliacao_biomedica/ e o teste ia
    # parar no relatório em vez de abrir a avaliação.
    tela.clicar_botao('Adicionar Avaliação de Saúde')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/avaliacao_biomedica/\d+/$'))
    tela.esperar().sucesso('Avaliação biomédica gerada com sucesso.')
    atendimento = _ultimo_atendimento(TipoAtendimento.AVALIACAO_BIOMEDICA)

    tela.ir(AVALIACAO_BIOMEDICA.format(atendimento.pk)).clicar_aba('Informações Adicionais')
    tela.aba('Informações Adicionais').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_INFORMACAO.format(atendimento.pk)}$'))
    tela.preencher('Informação Adicional', 'TextArea', 'Informação adicional E2E')
    tela.clicar_botao('Salvar').sucesso('Informação adicional registrada com sucesso.')
    assert InformacaoAdicional.objects.filter(atendimento=atendimento, informacao='Informação adicional E2E').exists(), (
        'a UI disse que salvou, mas a informação adicional não persistiu'
    )

    tela.ir(AVALIACAO_BIOMEDICA.format(atendimento.pk)).clicar_aba('Saúde Mental')
    tela.aba('Saúde Mental').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_SAUDEMENTAL.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [
            ('Tem ou já teve alguma questão de saúde mental?', 'Lista', 'Não'),
            ('Você já tentou se machucar alguma vez?', 'Lista', 'Não'),
            ('Que horário você costuma dormir?', 'Hora', '22:00'),
            ('Que horário você costuma acordar?', 'Hora', '06:00'),
            ('Como se sente ao acordar?', 'Lista', 'Disposto e com energia'),
            ('Como se sente ao longo do dia?', 'Lista', 'Disposto e com energia'),
            ('O que você costuma fazer 02 (duas) horas antes do sono?', 'Autocomplete Multiplo', 'Assistir televisão'),
            ('Você costuma usar telas antes de dormir?', 'Lista', 'Não'),
            ('Quanto tempo antes de dormir você para de usar telas?', 'Texto', '1 hora'),
            ('Você tem o hábito de usar telas para relaxar antes de dormir?', 'Lista', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Saúde mental registrada com sucesso.')
    saudemental = SaudeMental.objects.get(atendimento=atendimento)
    assert saudemental.hora_dormir == '22:00:00', 'a UI disse que salvou, mas a saúde mental não persistiu'
    assert saudemental.atividades_antes_sono.filter(descricao='Assistir televisão').exists(), 'a atividade antes do sono não persistiu'

    tela.ir(AVALIACAO_BIOMEDICA.format(atendimento.pk)).clicar_aba('Nutrição e Alimentação')
    tela.aba('Nutrição e Alimentação').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_NUTRICAO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [
            ('Apresentou perda de peso?', 'Lista', 'Não'),
            ('Apresentou ganho de peso?', 'Lista', 'Não'),
            ('Como você se sente em relação ao seu corpo?', 'Lista', 'Satisfeito(a)'),
            (
                'NOS ÚLTIMOS 30 DIAS, com que frequência você ficou com fome por não ter comida suficiente em sua casa?',
                'Lista',
                'Nunca',
            ),
            ('Quantas refeições faz por dia?', 'Lista', '3 refeições'),
            ('Possui alergia alimentar?', 'Lista', 'Não'),
            ('Possui intolerância alimentar?', 'Lista', 'Não'),
            ('Possui necessidade alimentar especial?', 'Lista', 'Não'),
            ('Você tem costume de realizar refeições assistindo à TV, mexendo no computador e/ou celular?', 'Radio', 'Não'),
            ('Quais refeições você faz ao longo do dia?', 'Checkbox Multiplo', 'Café da manhã'),
            ('Feijão?', 'Radio', 'Não'),
            ('Frutas frescas? (não considerar suco de frutas)', 'Radio', 'Não'),
            ('Verduras e/ou legumes? (não considerar batata, mandioca, aipim, macaxeira, cará e inhame)', 'Radio', 'Não'),
            ('Hambúrguer e/ou embutidos (presunto, mortadela, salame, linguiça, salsicha)?', 'Radio', 'Não'),
            (
                'Bebidas adoçadas (refrigerante, suco de caixinha, suco em pó, àgua de coco de caixinha, xaropes de guaraná/groselha, suco de fruta com adição de açúcar)?',
                'Radio',
                'Não',
            ),
            ('Macarrão instantâneo, salgadinhos de pacote ou biscoitos salgados?', 'Radio', 'Não'),
            ('Biscoito recheado, doces ou guloseimas (balas, pirulitos, chiclete, caramelo, gelatina)?', 'Radio', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Nutrição e alimentação registrada com sucesso.')
    nutricao = NutricaoAlimentacao.objects.filter(atendimento=atendimento).order_by('-id').first()
    assert nutricao is not None, 'a UI disse que salvou, mas a nutrição e alimentação não persistiu'
    assert nutricao.refeicoes_ao_dia.filter(descricao='Café da manhã').exists(), 'as refeições do dia não persistiram'

    # "Enviar Mensagem" só é oferecido na avaliação biomédica aberta, e é a única rota do
    # Saúde protegida por 2FA: o código de teste é fixo (`running_tests()` em
    # `TwoFactorAuthenticationCode.save`) e a tela o exibe em DEBUG.
    tela.ir(AVALIACAO_BIOMEDICA.format(atendimento.pk)).clicar_botao('Enviar Mensagem')
    expect(tela.pagina).to_have_url(re.compile(r'/djtools/two_factor_authentication/'))
    tela.preencher('Código', 'Número', '123456')
    tela.clicar_botao('Autenticar').sucesso('Código de autenticação validado com sucesso.')
    expect(tela.pagina).to_have_url(re.compile(rf'{ENVIAR_MENSAGEM.format(vinculo.pk, atendimento.pk)}$'))
    tela.preencher_formulario([('Título do Email', 'Texto', 'Mensagem E2E'), ('Mensagem do Email', 'TextArea', 'Corpo da mensagem E2E')])
    tela.clicar_botao('Enviar').sucesso('Mensagem enviada com sucesso.')


def test_hipotese_conduta_e_fechamento(logado_saude: Callable[[str], Page]) -> None:
    """O médico registra e edita hipótese e conduta, completa a anamnese e fecha o atendimento."""
    tela = Tela(logado_saude('medico'))

    from saude.models import CondutaMedica, HipoteseDiagnostica, TipoAtendimento

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    atendimento = _abrir_atendimento_medico(tela, vinculo.pk)
    assert atendimento.tipo == TipoAtendimento.ENFERMAGEM_MEDICO

    tela.ir(ATENDIMENTO_MEDICO.format(atendimento.pk)).clicar_aba('Hipótese Diagnóstica')
    tela.quadro('Hipótese Diagnóstica').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_HIPOTESE.format(atendimento.pk)}$'))
    tela.preencher_formulario([('CID', 'Autocomplete Multiplo', 'A001'), ('Sigilo', 'TextArea', 'Sigilo E2E')])
    tela.clicar_botao('Enviar').sucesso('Hipótese Diagnóstica registrada com sucesso.')
    hipotese = HipoteseDiagnostica.objects.get(atendimento=atendimento, sigilo='Sigilo E2E')
    assert hipotese.cid.codigo == 'A001', 'a UI disse que salvou, mas o CID não persistiu'

    tela.ir(ATENDIMENTO_MEDICO.format(atendimento.pk)).clicar_aba('Hipótese Diagnóstica')
    tela.quadro('Hipótese Diagnóstica').linha('A001').clicar_botao('Editar')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_HIPOTESE.format(hipotese.pk)}$'))
    tela.preencher('Sigilo', 'TextArea', 'Sigilo E2E revisado')
    tela.clicar_botao('Salvar').sucesso('Hipótese Diagnóstica alterada com sucesso.')
    hipotese.refresh_from_db()
    assert hipotese.sigilo == 'Sigilo E2E revisado', 'a UI disse que editou, mas o sigilo não mudou'

    tela.ir(ATENDIMENTO_MEDICO.format(atendimento.pk)).clicar_aba('Hipótese Diagnóstica')
    tela.quadro('Conduta Médica').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_CONDUTA.format(atendimento.pk)}$'))
    tela.preencher('Conduta', 'TextArea', 'Conduta médica E2E')
    tela.clicar_botao('Salvar').sucesso('Conduta Médica registrada com sucesso.')
    conduta = CondutaMedica.objects.get(atendimento=atendimento, conduta='Conduta médica E2E')

    tela.ir(ATENDIMENTO_MEDICO.format(atendimento.pk)).clicar_aba('Hipótese Diagnóstica')
    tela.quadro('Conduta Médica').linha('Conduta médica E2E').clicar_botao('Editar')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_CONDUTA.format(conduta.pk)}$'))
    tela.preencher('Conduta', 'TextArea', 'Conduta médica E2E revisada')
    tela.clicar_botao('Salvar').sucesso('Conduta Médica alterada com sucesso.')
    conduta.refresh_from_db()
    assert conduta.conduta == 'Conduta médica E2E revisada', 'a UI disse que editou, mas a conduta não mudou'

    # O fechamento exige (Motivo + Intervenção) ou (Anamnese + Conduta); a conduta já existe,
    # então a anamnese é o que falta para o produto liberar o "Fechar".
    tela.ir(ADICIONAR_ANAMNESE.format(atendimento.pk))
    tela.preencher('HDA', 'TextArea', 'Anamnese E2E')
    tela.clicar_botao('Salvar').sucesso('Anamnese registrada com sucesso.')

    tela.ir(ATENDIMENTO_MEDICO.format(atendimento.pk)).clicar_link('Fechar')
    expect(tela.pagina).to_have_url(re.compile(rf'{FECHAR_ATENDIMENTO.format(atendimento.pk)}$'))
    tela.esperar().preencher('Observação de Fechamento', 'TextArea', 'Fechamento E2E')
    tela.clicar_botao('Salvar').sucesso('Atendimento fechado com sucesso.')


def test_cancelar_e_reabrir_atendimento(logado_saude: Callable[[str], Page]) -> None:
    """O auxiliar cancela um atendimento aberto e o coordenador reabre um fechado."""
    auxiliar = Tela(logado_saude('auxiliar_enfermagem'))

    from saude.models import Atendimento, SituacaoAtendimento, TipoAtendimento

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'

    # A cadeia já deixou atendimentos médico/enfermagem fechados (o de `test_02` e o de
    # `test_hipotese`); reabrir qualquer um deles é o fluxo do coordenador.
    fechado = (
        Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=TipoAtendimento.ENFERMAGEM_MEDICO, situacao=SituacaoAtendimento.FECHADO)
        .order_by('id')
        .first()
    )
    assert fechado is not None, 'nenhum atendimento fechado na cadeia: rode a suíte inteira'

    cancelado = _abrir_atendimento_medico(auxiliar, vinculo.pk)
    auxiliar.clicar_link('Cancelar')
    expect(auxiliar.pagina).to_have_url(re.compile(rf'{CANCELAR_ATENDIMENTO.format(cancelado.pk)}$'))
    auxiliar.esperar().preencher('Observação de Cancelamento', 'TextArea', 'Cancelamento E2E')
    auxiliar.clicar_botao('Salvar').sucesso('Atendimento cancelado com sucesso.')
    cancelado.refresh_from_db()
    assert cancelado.situacao == SituacaoAtendimento.CANCELADO, 'a UI disse que cancelou, mas o atendimento continua aberto'

    # Só o atendimento FECHADO oferece "Reabrir" (a barra de ações distingue cancelado de
    # fechado), e quem tem o grupo e a permissão é o coordenador sistêmico.
    coordenador = Tela(logado_saude('coordenador_sistemico'))
    coordenador.ir(ATENDIMENTO_MEDICO.format(fechado.pk))
    expect(coordenador.botao('Reabrir')).to_have_attribute('href', REABRIR_ATENDIMENTO.format(fechado.pk))
    coordenador.clicar_botao('Reabrir').sucesso('Atendimento reaberto com sucesso.')
    fechado.refresh_from_db()
    assert fechado.situacao == SituacaoAtendimento.REABERTO, 'a UI disse que reabriu, mas o atendimento continua fechado'


def test_editar_cartao_sus(logado_saude: Callable[[str], Page]) -> None:
    """O coordenador grava o número do Cartão SUS do aluno pelo prontuário (popup)."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    from edu.models import Aluno

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_botao('Editar Cartão SUS')
    popup = tela.popup()
    # O popup é um iframe: a URL da página de trás não muda, então a rota é afirmada no `src`.
    expect(tela.pagina.locator('iframe.fancybox-iframe')).to_have_attribute('src', re.compile(rf'{EDITAR_CARTAO_SUS.format(aluno.pk)}\?_popup=1$'))
    popup.preencher('Cartão SUS', 'Texto', '898 0012 3456 7890')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Número SUS cadastrado com sucesso.')
    aluno.refresh_from_db()
    assert aluno.cartao_sus == '898 0012 3456 7890', 'a UI disse que salvou, mas o Cartão SUS não persistiu'


def test_cadastrar_pessoa_externa(logado_saude: Callable[[str], Page]) -> None:
    """O enfermeiro cadastra uma pessoa externa e o sistema abre o prontuário dela."""
    tela = Tela(logado_saude('enfermeiro'))

    from pycpfcnpj import gen
    from rh.models import PessoaExterna

    from saude.models import Prontuario

    # CPF novo a cada execução: a suíte não dá flush e a validação recusa CPF já cadastrado.
    # O campo devolve o CPF mascarado (`BrCpfField.clean`), então a busca usa a mesma máscara.
    cpf = gen.cpf()
    cpf_mascarado = f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'
    tela.ir(PRONTUARIOS).ver_titulo('Prontuários').clicar_botao('Adicionar Atendimento Externo')
    expect(tela.pagina).to_have_url(re.compile(rf'{CADASTRAR_PESSOA_EXTERNA}$'))
    tela.preencher_formulario(
        [
            ('Nome', 'Texto', 'Pessoa Externa E2E'),
            ('CPF', 'Texto', cpf),
            ('Data de Nascimento', 'Data', '10/05/1990'),
            ('Nome da Mãe', 'Texto', 'Mãe da Pessoa Externa E2E'),
            ('Sexo', 'Lista', 'Masculino'),
        ]
    )
    tela.clicar_botao('Salvar')
    pessoa = PessoaExterna.objects.get(cpf=cpf_mascarado)
    tela.esperar().ver_titulo('Prontuário')
    assert pessoa.nome == 'Pessoa Externa E2E', 'a UI abriu o prontuário, mas a pessoa externa não persistiu'
    assert Prontuario.objects.filter(vinculo=pessoa.get_vinculo()).exists(), 'a pessoa externa não ganhou prontuário'


def test_lista_de_alunos_por_alergia(logado_saude: Callable[[str], Page]) -> None:
    """O relatório de alergias lista o aluno do campus a partir do processo saúde-doença."""
    tela = Tela(logado_saude('enfermeiro'))

    from saude.models import ProcessoSaudeDoenca, TipoAtendimento

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    atendimento = _abrir_atendimento_medico(tela, vinculo.pk)
    assert atendimento.tipo == TipoAtendimento.ENFERMAGEM_MEDICO

    # A lista só considera atendimentos médico/enfermagem com processo saúde-doença preenchido,
    # e `Atendimento.abrir` COPIA o processo mais recente do prontuário para o novo atendimento:
    # por isso o box já oferece "Editar" quando a cadeia preencheu a ficha antes.
    tela.clicar_aba('Antecedentes')
    processo = tela.quadro('Processo Saúde-Doença')
    botao = 'Editar' if ProcessoSaudeDoenca.objects.filter(atendimento=atendimento).exists() else 'Adicionar'
    processo.clicar_botao(botao)
    tela.preencher_formulario(
        [
            ('Já fez alguma cirurgia?', 'Lista', 'Não'),
            ('Histórico de hemorragia?', 'Lista', 'Não'),
            ('Alergia a medicamentos?', 'Lista', 'Não'),
            ('Faz uso de medicamentos rotineiramente?', 'Lista', 'Não'),
            ('Tem Plano de Saúde?', 'Lista', 'Não'),
            ('Tem Plano Odontológico?', 'Lista', 'Não'),
            ('Já teve lesão nos músculos ou nos ossos?', 'Lista', 'Não'),
            ('Sofre de alguma doença crônica?', 'Lista', 'Não'),
            ('Doenças Prévias?', 'Lista', 'Não'),
            ('Problemas Auditivos?', 'Lista', 'Não'),
            ('É pessoa com deficiência?', 'Lista', 'Não'),
            ('Tem transtorno de neurodesenvolvimento?', 'Lista', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Processo Saúde-Doença registrado com sucesso.')
    assert ProcessoSaudeDoenca.objects.filter(atendimento=atendimento).exists(), 'a UI disse que salvou, mas o processo saúde-doença não persistiu'

    tela.ir(LISTA_ALUNOS).ver_titulo('Lista de Alunos')
    # O filtro de campus é o UO do setor de quem abriu o atendimento — é por ele que a lista
    # seleciona os atendimentos médico/enfermagem.
    campus = atendimento.usuario_aberto.get_vinculo().setor.uo
    # A tela do relatório não usa o invólucro `.search-and-filters`: o formulário é o corpo.
    tela.preencher('Campus', 'Lista', str(campus))
    tela.preencher('Nome', 'Checkbox', 'marcar')
    tela.clicar_botao('Enviar')
    tela.ver_texto('Lista dos alunos').ver_texto('Aluno Saúde')
