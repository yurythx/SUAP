"""Fatia 4 da doc de usuário do ``comum`` — documentos: assinar, autenticar, despachar, telefonar.

Reúne o que o SUAP faz com **papel**: a assinatura digital de um PDF (guardar o certificado,
assinar, conferir quem assinou), a autenticação pública do documento que a instituição emitiu,
o despacho das solicitações de documento funcional e a lista telefônica dos setores.

É também a fatia que escreve a seção **Para o público externo** da doc: autenticar um documento
pelo código do rodapé e validar a assinatura de um PDF são os dois únicos fluxos do ``comum``
que rodam **sem conta no SUAP**, e é essa promessa — impressa no QR code de todo documento
assinado — que os dois últimos testes deste arquivo exercitam em página anônima.

Cada teste é o roteiro de UMA tarefa da doc, na ordem em que ela as apresenta; as asserções
existem para a rodada falhar alto quando a tela muda de forma, e as ``anotar`` despejam
rótulos/opções que a redação copia em vez de deduzir de ``views.py``.

**A costura que esta fatia não consegue fechar**, e por isso a declara na doc como
pré-condição: o ``.p12`` versionado expirou em 26/11/2024, ``CertificadoDigitalForm.save``
grava no cadastro a validade lida do próprio arquivo e ``AssinarDocumentoForm`` só oferece
certificado com ``validade__gte=hoje``. Quer dizer: o certificado que o teste cadastra pela
tela nunca poderia assinar. Os dois lados são exercitados de propósito — o cadastro pela tela
(que é o passo da doc) e a ausência dele na lista de assinatura (que é a regra da doc).

O leitor de arquivos do SIAFI (``/comum/ver_arquivo_siafi/``) **ficou de fora**: até #17394 o
``<form method=post>`` de ``comum/templates/ver_arquivo_siafi.html`` não tinha
``{% csrf_token %}`` e o envio respondia **HTTP 403** em qualquer navegador (medido nesta rodada).
O processamento é coberto por ``comum/tests/fluxos/test_fluxo_arquivo_siafi.py`` e o envio pelo
navegador por ``comum/tests/e2e/test_ferramentas_apoio.py``.

Nenhuma tarefa desta fatia veio de ``.feature``: as cinco do ``comum`` são de cadastro e de
senha. As tarefas 20 a 23 e a seção do público externo foram **propostas** a partir do
``menu.yaml``, do admin e do encadeamento das telas.
"""

from __future__ import annotations

import pytest

from comum.tests.doc.conftest import (
    JUSTIFICATIVA_DOC,
    NOME_SETOR_DOC,
    RAMAL_DO_SETOR_DOC,
    RAMAL_NOVO_DOC,
    SIGLA_SETOR_DOC,
    TELEFONE_DO_SETOR_DOC,
    TIPO_SOLICITADO_DOC,
    anotar,
)
from comum.tests.e2e.conftest import ARQUIVO_P12, ARQUIVO_PDF, ARQUIVO_PDF_ASSINADO, ASSINANTE, SENHA_DO_CERTIFICADO
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

CERTIFICADOS = '/admin/comum/certificadodigital/'
ASSINAR = '/comum/assinar_documento/'
ASSINAR_ICPEDU = '/comum/assinar_documento_icpedu/'
VERIFICAR = '/comum/verificar_documento/'
VALIDAR = '/comum/validar_assinatura/'
AUTENTICAR = '/comum/autenticar_documento/'
BAIXAR = '/comum/baixar_documento/{pk}/{codigo}/'
REGISTROS_EMISSAO = '/admin/comum/registroemissaodocumento/'
MEUS_DOCUMENTOS = '/comum/documentos_emitidos_suap/'
SOLICITACOES = '/admin/comum/documentocontrole/'
VER_SOLICITACAO = '/comum/ver_solicitacao_documento/{pk}/'
TELEFONES = '/comum/telefones/'
PAGINA_DO_SETOR = '/rh/setor/{pk}/'
ADICIONAR_TELEFONE = '/comum/setor_adicionar_telefone/{setor}/'

# O e-mail institucional que a tarefa dos telefones grava no setor. Fixo porque aparece na
# captura da página do setor, e derivado da sigla porque é assim que a instituição os nomeia.
EMAIL_DO_SETOR_DOC = f'{SIGLA_SETOR_DOC.lower()}@ifrn.edu.br'


def _opcoes_de_certificado(tela: Tela) -> list[str]:
    """Rótulos oferecidos no campo *Certificado* da tela de assinatura.

    Existe para a doc poder afirmar o que a lista **não** traz: é a única forma de observar o
    filtro ``validade__gte=hoje`` de ``AssinarDocumentoForm`` sem ler o formulário.
    """
    return [texto.strip() for texto in tela.loc('//select[@name="certificado"]/option').all_inner_texts() if texto.strip() not in ('', '---------')]


def test_guardar_certificado_digital(logado_comum, certificados_do_papel, certificado_alheio, capturar):
    """Tarefa 20, etapa 1 — guardar o certificado no SUAP, pela tela.

    Três coisas de uma vez, porque as três são a mesma tela e a mesma frase da doc:

    * o cadastro em si — o formulário pede **só** o arquivo e a senha, e extrai do ``.p12`` o
      nome, a organização, a unidade e a validade (``CertificadoDigitalForm.save``). Nada disso
      é digitado, e a doc precisa dizer isso;
    * o **recorte por dono**: o certificado de outra pessoa não aparece na listagem. Medido na
      tela, e não lido de ``CertificadoDigitalAdmin.get_queryset``;
    * a **validade**, que é a pré-condição da etapa 2. O arquivo versionado expirou em
      26/11/2024, então o cadastro nasce vencido e o certificado não chega à lista da tela de
      assinatura. É o que o último bloco afirma — e é a única forma honesta de documentar a
      regra sem gerar um par chave/certificado novo.
    """
    from comum.models import CertificadoDigital

    pagina = logado_comum('diretor_geral')

    tela = Tela(pagina).ir(CERTIFICADOS)
    tela.ver_titulo('Certificados Digitais')
    anotar('certificados-listagem', tela)
    tela.clicar_botao('Adicionar Certificado Digital')
    tela.esperar()
    anotar('certificado-formulario', tela)
    tela.preencher_formulario(
        [
            ('Arquivo', 'arquivo real', ARQUIVO_P12),
            ('Senha do Certificado', 'senha', SENHA_DO_CERTIFICADO),
        ]
    )
    capturar(pagina, 'certificado-formulario')
    tela.clicar_botao('Salvar')

    guardado = CertificadoDigital.objects.filter(user=certificados_do_papel).first()
    assert guardado, 'a tela aceitou o certificado, mas o cadastro não persistiu'
    assert guardado.nome == ASSINANTE, f'o cadastro não extraiu o titular do arquivo: {guardado.nome!r}'
    assert guardado.validade.year == 2024, f'a validade não veio do arquivo: {guardado.validade}'

    # O admin do SUAP não volta para a listagem depois de salvar (armadilha 2 da fatia 1).
    tela.ir(CERTIFICADOS)
    tela.ver_texto(ASSINANTE)
    assert certificado_alheio.nome not in pagina.content(), 'a listagem mostrou o certificado de outra pessoa'
    capturar(pagina, 'certificados-listagem')

    # A regra que a doc afirma como pré-condição: vencido, ele fica no cadastro e some da
    # assinatura.
    assinatura = Tela(pagina).ir(ASSINAR)
    # Sem abrir a tela, a lista vazia de um 403 faria a asserção abaixo passar à toa.
    assinatura.ver_titulo('Assinar Documento')
    assert str(guardado) not in _opcoes_de_certificado(assinatura), (
        f'o certificado vencido foi oferecido para assinar: {_opcoes_de_certificado(assinatura)}'
    )


def _e_o_post_da_assinatura(resposta) -> bool:
    """Casa a resposta do POST que assina — e não a do GET que carregou o formulário."""
    return ASSINAR in resposta.url and resposta.request.method == 'POST'


def test_assinar_documento_em_pdf(logado_comum, certificado_digital, capturar):
    """Tarefa 20, etapa 2 — assinar um PDF e receber de volta o arquivo assinado.

    **Dois** capturadores, e não um, pelo motivo medido no e2e: a view devolve o PDF com
    ``Content-Disposition: inline``, mas o Chromium headless trata a navegação como download e
    descarta o corpo do lado do protocolo (``Protocol error (Network.getResponseBody)``). Os
    cabeçalhos vêm da resposta; os **bytes**, do arquivo baixado.

    A asserção final é que o PDF que saiu é **verificável** pela mesma pilha que a tela pública
    de validação usa — assinar sem poder validar depois não é assinar, e é essa a promessa que a
    doc faz ao leitor na etapa 3 e na seção do público externo.
    """
    pagina = logado_comum('diretor_geral')

    tela = Tela(pagina).ir(ASSINAR)
    tela.ver_titulo('Assinar Documento')
    anotar('assinar-formulario', tela)
    assert str(certificado_digital) in _opcoes_de_certificado(tela), 'o certificado dentro da validade não foi oferecido para assinar'
    tela.preencher_formulario(
        [
            ('Arquivo PDF', 'arquivo real', ARQUIVO_PDF),
            ('Certificado', 'lista', str(certificado_digital)),
            ('Senha do Certificado', 'senha', SENHA_DO_CERTIFICADO),
        ]
    )
    capturar(pagina, 'assinar-formulario')

    with pagina.expect_download() as baixado, pagina.expect_response(_e_o_post_da_assinatura) as captura:
        tela.clicar_botao('Enviar')
    resposta = captura.value

    assert resposta.status == 200, f'a tela de assinatura respondeu HTTP {resposta.status}'
    assert resposta.headers['content-type'] == 'application/pdf', f'a tela devolveu {resposta.headers["content-type"]!r} em vez do PDF assinado'

    with open(baixado.value.path(), 'rb') as assinado:
        conteudo = assinado.read()
    assert _assinantes_do_pdf(conteudo) == [ASSINANTE], 'o PDF voltou da tela, mas sem assinatura digital verificável'


def _assinantes_do_pdf(conteudo: bytes) -> list[str]:
    """Os nomes comuns (CN) das assinaturas de um PDF em memória, pela pilha de produção."""
    import tempfile

    from comum import signer

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as arquivo:
        arquivo.write(conteudo)
    return [assinatura['cn'] for assinatura in signer.verify(arquivo.name)]


def test_conferir_a_assinatura_de_um_pdf(logado_comum, capturar):
    """Tarefa 20, etapa 3 — a tela interna que diz quem assinou um PDF recebido.

    Separada da etapa 2 porque parte de outro lugar (o arquivo chegou de fora, e quem confere
    não precisa ter certificado nenhum) e porque o desfecho que a doc cita é a **mensagem**, não
    um download.
    """
    pagina = logado_comum('diretor_geral')

    tela = Tela(pagina).ir(VERIFICAR)
    tela.ver_titulo('Verificar Documento')
    anotar('verificar-assinatura', tela)
    tela.preencher('Arquivo', 'arquivo real', ARQUIVO_PDF_ASSINADO)
    tela.clicar_botao('Enviar')

    tela.sucesso(f'Documento assinado digitalmente por {ASSINANTE}.')
    capturar(pagina, 'verificar-assinatura')


def test_assinatura_em_nuvem_avisa_quando_o_servico_esta_fora(logado_comum):
    """Tarefa 20, nota — a assinatura em nuvem (ICP EDU) avisa em vez de quebrar.

    Papel superusuário, e medido: ``assinar_documento_icpedu`` exige ``comum.change_user``, que
    **nenhum** grupo do ``permissions.yaml`` concede (``bin/scripts/papeis.py``) — nenhum papel de
    ``PAPEIS`` abre esta tela, e com ``gestor_pessoal`` a rodada só via a página de 403. É por
    isso que a doc cita o serviço numa nota, e não num passo.

    O estado é o normal do SUAP fora de produção: ``comum/fixtures/apis_externas.json`` instala a
    ``APIExterna`` ICPEDU com ``ativo: false``. Entra pela tela de assinatura local primeiro
    porque a view responde ``httprr('..')``, que resolve o destino pelo *breadcrumb* da sessão —
    sem uma tela anterior registrada o navegador entraria em laço de redirecionamento.
    """
    tela = Tela(logado_comum('admin')).ir(ASSINAR)
    tela.ir(ASSINAR_ICPEDU)

    tela.erro('O serviço de assinatura ICP EDU está temporariamente indisponível')


def test_atender_uma_solicitacao_de_documento(logado_comum, solicitacao_documento, capturar):
    """Tarefa 21 — acompanhar a solicitação de documento funcional e atendê-la.

    O caminho é o real: a listagem do admin, o ícone de exibição da linha (a solicitação publica
    ``get_absolute_url``) e o botão da própria tela de acompanhamento. O endereço de atendimento
    não é montado pelo teste — é o ``href`` do botão —, que é o que liga a ação à solicitação
    certa.

    A listagem publica as duas ações na própria linha (``DocumentoControleAdmin.get_acoes``), e
    é por isso que a asserção do meio existe: ``get_acoes`` **não** está em ``list_display``, o
    que pela leitura do código faria os botões nunca renderizarem. Renderizam — medido —, e a
    doc descreve o caminho pela tela de acompanhamento porque é o que dá ao despachante o
    histórico antes da decisão.

    A mensagem de sucesso só sai quando o registro muda (#17393); a asserção no ORM confirma o
    desfecho que a tela anunciou.
    """
    from djtools.choices import SituacaoSolicitacaoDocumento

    from comum.models import DocumentoControle

    _, solicitacao = solicitacao_documento
    pagina = logado_comum('gestor_pessoal')

    tela = Tela(pagina).ir(SOLICITACOES)
    tela.ver_titulo('Solicitações de Documento')
    anotar('documentos-solicitacoes-listagem', tela)
    capturar(pagina, 'documentos-solicitacoes-listagem')
    assert tela.loc(f'//a[@href="/comum/rejeitar_solicitacao/{solicitacao.pk}/"]').count(), 'a linha deixou de oferecer a rejeição'

    tela.linha(TIPO_SOLICITADO_DOC).clicar_icone('exibição')
    tela.esperar()
    assert VER_SOLICITACAO.format(pk=solicitacao.pk) in pagina.url, f'o ícone da linha não levou à solicitação: {pagina.url}'
    tela.ver_texto('Histórico da Solicitação')
    tela.ver_texto(JUSTIFICATIVA_DOC)
    tela.ver_texto('Não Atendida')
    anotar('solicitacao-acompanhamento', tela)
    capturar(pagina, 'solicitacao-acompanhamento')

    tela.clicar_botao('Marcar Solicitação como Atendida')
    tela.sucesso('Solicitação atendida com sucesso.')
    assert DocumentoControle.objects.get(pk=solicitacao.pk).status_solicitacao == SituacaoSolicitacaoDocumento.ATENDIDA, (
        'a UI disse que atendeu, mas a situação da solicitação não mudou'
    )


def test_rejeitar_uma_solicitacao_de_documento(logado_comum, solicitacao_documento, capturar):
    """Tarefa 21, alternativa — recusar a solicitação registrando o motivo.

    Teste separado, e não um passo a mais do anterior, porque atender e rejeitar **consomem** a
    mesma solicitação: ``pode_atender_solicitacao`` exige a situação *Não Atendida*, de modo que
    a segunda transição no mesmo registro passaria sem fazer nada e a doc afirmaria um desfecho
    que não aconteceu.

    A rejeição é o botão ``btn danger popup`` da linha: abre em fancybox dentro de um iframe, e
    o ``httprr('..')`` da view devolve ``close_fancybox()`` porque o link carrega ``_popup=1`` —
    a mensagem aparece na página de trás, recarregada (armadilha 1 da fatia 1).

    O motivo é afirmado no histórico, e não só na situação: rejeição sem motivo gravado é
    indistinguível de rejeição por engano quando o servidor reclamar.
    """
    from djtools.choices import SituacaoSolicitacaoDocumento

    from comum.models import DocumentoControle, DocumentoControleHistorico

    _, solicitacao = solicitacao_documento
    motivo = 'O crachá anterior ainda está dentro da validade.'
    pagina = logado_comum('gestor_pessoal')

    tela = Tela(pagina).ir(SOLICITACOES)
    tela.linha(TIPO_SOLICITADO_DOC).clicar_botao('Rejeitar Solicitação')
    popup = tela.popup()
    anotar('solicitacao-rejeitar', popup)
    popup.preencher('Motivo', 'textarea', motivo)
    capturar(pagina, 'solicitacao-rejeitar')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Solicitação rejeitada com sucesso.')
    assert DocumentoControle.objects.get(pk=solicitacao.pk).status_solicitacao == SituacaoSolicitacaoDocumento.REJEITADA, (
        'a UI disse que rejeitou, mas a situação da solicitação não mudou'
    )
    assert DocumentoControleHistorico.objects.filter(solicitacao=solicitacao, motivo=motivo).exists(), (
        'a rejeição não registrou o motivo no histórico da solicitação'
    )


def test_meus_documentos_emitidos(logado_comum, capturar):
    """Tarefa 22, etapa 1 — o índice pessoal dos documentos que a pessoa pode emitir.

    A tela é um *fan-out* por sinal (``djtools.documentos.signal``): nove aplicações respondem a
    ele, e uma exceção em qualquer uma derruba o índice inteiro. O estado vazio é o que há para
    afirmar aqui — as fontes são de outros módulos e montá-las inverteria a dependência entre os
    apps —, e é ele que a captura mostra.
    """
    pagina = logado_comum('solicitante')

    tela = Tela(pagina).ir(MEUS_DOCUMENTOS)
    tela.ver_titulo('Meus Documentos SUAP')
    tela.ver_texto('Não há documentos.')
    anotar('meus-documentos', tela)
    capturar(pagina, 'meus-documentos')


def test_registros_de_emissao_e_cancelamento(logado_comum, registro_emissao_documento, capturar):
    """Tarefa 22, etapa 2 — a trilha dos documentos emitidos e o cancelamento de um deles.

    O papel é o superusuário do seed, e é uma exceção deliberada à regra de não cair para o
    ``admin``: ``comum.view_registroemissaodocumento`` não pertence a **nenhum** grupo do
    ``permissions.yaml`` (medido com ``bin/scripts/papeis.py``), de modo que não existe papel de
    ``PAPEIS`` que abra esta tela.

    O cancelamento é executado pela ação em massa da listagem, que é o único caminho: não há
    botão de linha. A asserção é no ORM, porque ``cancelar`` é um ``queryset.update`` mudo — a
    listagem só reflete o estado na coluna *Cancelado* depois de recarregada.
    """
    from comum.models import RegistroEmissaoDocumento

    pagina = logado_comum('admin')

    tela = Tela(pagina).ir(REGISTROS_EMISSAO)
    tela.ver_titulo('Registros de Emissão de Documento')
    anotar('registros-emissao', tela)
    capturar(pagina, 'registros-emissao')
    tela.ver_texto(registro_emissao_documento.codigo_verificador)

    tela.linha(registro_emissao_documento.codigo_verificador).loc('//input[@name="_selected_action"]').first.check()
    tela.loc('//select[@name="action"]').first.select_option(label='Cancelar')
    tela.clicar_botao('Aplicar')
    tela.esperar()

    assert RegistroEmissaoDocumento.objects.get(pk=registro_emissao_documento.pk).cancelado, (
        'a ação foi executada, mas o registro não ficou marcado como cancelado'
    )


def test_telefones_e_email_do_setor(logado_comum, telefone_do_setor, capturar):
    """Tarefa 23 — achar um ramal na lista telefônica e manter os contatos de um setor.

    Um teste para o ciclo inteiro porque a manutenção **é** o desfecho da consulta: quem abre a
    lista e vê o ramal errado é quem vai corrigi-lo, e o caminho até o formulário passa pela
    página do setor (o nome do setor na lista é o link).

    A navegação é por clique, e não por ``goto`` na rota — é o que separa este roteiro do e2e
    (armadilha 2 da fatia 3): *Editar Telefones* e *Editar E-mail* só aparecem para quem tem
    ``rh.pode_gerenciar_setor_telefone`` **ou** chefia o setor
    (``rh/templates/setor.html:12``), e a doc afirma o clique.

    A remoção é por GET, sem confirmação (``comum/views.py``): é por isso que o alvo é um
    telefone criado por este teste, num setor descartável.
    """
    from comum.models import SetorTelefone
    from rh.models import Setor

    setor = telefone_do_setor.setor
    pagina = logado_comum('gestor_pessoal')

    tela = Tela(pagina).ir(TELEFONES)
    tela.ver_titulo('Telefones')
    tela.ver_texto(NOME_SETOR_DOC)
    tela.ver_texto(TELEFONE_DO_SETOR_DOC)
    anotar('telefones-lista', tela)
    capturar(pagina, 'telefones-lista')

    tela.ir(PAGINA_DO_SETOR.format(pk=setor.pk))
    tela.esperar()
    anotar('setor-pagina', tela)
    tela.clicar_botao('Editar Telefones')
    tela.esperar()
    assert ADICIONAR_TELEFONE.format(setor=setor.pk) in pagina.url, f'o botão da página do setor não levou aos telefones: {pagina.url}'

    tela.preencher_formulario(
        [
            ('Número telefônico', 'texto', '(84) 4005-4711'),
            ('Ramal', 'texto', RAMAL_NOVO_DOC),
            ('Observação', 'texto', 'Sala de reuniões'),
        ]
    )
    capturar(pagina, 'setor-telefones')
    tela.clicar_botao('Enviar')

    tela.sucesso('Telefone adicionado com sucesso.')
    novo = SetorTelefone.objects.filter(setor=setor, ramal=RAMAL_NOVO_DOC).first()
    assert novo, 'a UI disse que adicionou, mas o telefone não persistiu'

    tela.linha(RAMAL_NOVO_DOC).clicar_botao('Remover')
    tela.sucesso('Telefone removido com sucesso.')
    assert not SetorTelefone.objects.filter(pk=novo.pk).exists(), 'a UI disse que removeu, mas o telefone continua no banco'
    assert SetorTelefone.objects.filter(pk=telefone_do_setor.pk).exists(), 'a remoção levou junto o telefone da linha de cima'

    tela.ir(PAGINA_DO_SETOR.format(pk=setor.pk))
    tela.clicar_botao('Editar E-mail')
    tela.esperar()
    tela.preencher('E-mail', 'texto', EMAIL_DO_SETOR_DOC)
    tela.clicar_botao('Salvar')

    tela.sucesso('E-mail editado com sucesso.')
    assert Setor.objects.get(pk=setor.pk).email == EMAIL_DO_SETOR_DOC, 'a UI disse que editou, mas o e-mail do setor não persistiu'


# ---------------------------------------------------------------------------------------
# Para o público externo — os dois fluxos do `comum` que rodam SEM conta no SUAP
# ---------------------------------------------------------------------------------------


def test_autenticar_um_documento_sem_login(pagina_anonima, registro_emissao_documento, capturar):
    """Público externo — autenticar pelo trio do rodapé e baixar o original em PDF.

    Em página anônima de propósito: é a promessa impressa no QR code de todo documento que o
    SUAP emite, e quem confere o papel é justamente quem não tem conta. Se a tela passar a
    exigir login, todo documento já entregue fica sem como ser conferido.

    O endereço do download não é adivinhado pelo teste — é o ``href`` que a própria tela
    publica. Afirmá-lo antes de buscá-lo é o que mede o contrato (a tela aponta para o registro
    certo) em vez de uma coincidência de URL montada por fora.

    O reCAPTCHA do formulário não atrapalha: ``ReCaptchaField.validate`` devolve ``True`` sob
    teste, antes mesmo da checagem de obrigatoriedade. **A doc menciona o desafio**, porque o
    usuário real o vê.
    """
    registro = registro_emissao_documento
    url_do_pdf = BAIXAR.format(pk=registro.pk, codigo=registro.codigo_verificador)

    tela = Tela(pagina_anonima).ir(AUTENTICAR)
    tela.ver_titulo('Verificação de Autenticação de Documento')
    anotar('autenticar-formulario', tela)
    tela.preencher_formulario(
        [
            ('Tipo de Documento', 'lista', registro.tipo),
            ('Data da Emissão', 'data', registro.data_emissao.strftime('%d/%m/%Y')),
            ('Código Verificador', 'texto', registro.codigo_verificador),
        ]
    )
    capturar(pagina_anonima, 'autenticar-formulario')
    tela.clicar_botao('Enviar')

    tela.ver_texto('Documento autenticado com sucesso.')
    tela.ver_texto(ASSINANTE)
    anotar('autenticar-resultado', tela)
    capturar(pagina_anonima, 'autenticar-resultado')

    link = tela.loc(f'//a[@href="{url_do_pdf}"]').first
    assert link.count(), f'a tela autenticou o documento mas não ofereceu o download em {url_do_pdf}'

    pdf = tela.buscar(url_do_pdf)
    assert pdf.status == 200, f'o download do documento autenticado respondeu HTTP {pdf.status}'
    assert pdf.headers['content-type'] == 'application/pdf', f'o download veio como {pdf.headers["content-type"]!r}'


def test_autenticacao_de_codigo_inexistente(pagina_anonima, registro_emissao_documento):
    """Público externo — o código que não existe tem de dizer isso, e nunca autenticar por engano.

    O contraexemplo importa porque a busca é por ``codigo_verificador__startswith`` dentro de uma
    janela de dois dias: é um filtro frouxo por construção, e o que impede um código inventado de
    casar com um documento real é só ele. Sem captura — a doc cita a mensagem.
    """
    tela = Tela(pagina_anonima).ir(AUTENTICAR)
    tela.preencher_formulario(
        [
            ('Tipo de Documento', 'lista', registro_emissao_documento.tipo),
            ('Data da Emissão', 'data', registro_emissao_documento.data_emissao.strftime('%d/%m/%Y')),
            ('Código Verificador', 'texto', 'ZZZZZZZZZZ'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_texto('Documento não autenticado.')


def test_validar_a_assinatura_sem_login(pagina_anonima, capturar):
    """Público externo — jogar o PDF na tela e ver quem assinou, sem conta no SUAP.

    É o par da tarefa 20: o carimbo que ``comum/signer.py`` grava em toda assinatura do SUAP
    traz o endereço **desta** tela no QR code. A asserção cobre as três linhas que a tela
    imprime por assinatura (quem, quando, e que o documento não foi alterado depois), porque são
    elas que a doc transcreve.
    """
    tela = Tela(pagina_anonima).ir(VALIDAR)
    tela.ver_titulo('Validar Assinatura')
    anotar('validar-assinatura', tela)
    tela.preencher('Arquivo', 'arquivo real', ARQUIVO_PDF_ASSINADO)
    tela.clicar_botao('Enviar')

    tela.ver_texto('foram detectadas')
    tela.ver_texto(ASSINANTE)
    tela.ver_texto('A assinatura é')
    tela.ver_texto('Documento não foi alterado após assinatura.')
    capturar(pagina_anonima, 'validar-assinatura')
