"""Telas da importação SIAPE."""

from datetime import datetime
from unittest import mock

import pytest
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from comum.models import Configuracao, Log
from rh.importacao_siape.armazenamento import arquivos_da_pasta
from rh.models import ImportacaoSiape, ImportacaoSiapeLote, ImportacaoSiapeOcorrencia
from rh.tests.siape import zip_do_extrator

pytestmark = pytest.mark.usefixtures('importacao_serial', 'limpar_importacoes')


@pytest.fixture
def cliente(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def lotes_pequenos():
    """`CAREMPR.TXT` do zip de teste tem só 2 linhas: tamanho 1 força o `cargo_emprego` a dividir em lotes."""
    Configuracao.objects.update_or_create(app='rh', chave='importacao_siape_tamanho_lote', defaults={'valor': '1'})
    Configuracao.clear_cache()
    yield
    Configuracao.clear_cache()


def _upload(cliente: Client, nome: str, conteudo: bytes | None = None):
    dados = {'arquivo': SimpleUploadedFile(nome, conteudo or zip_do_extrator())}
    return cliente.post('/rh/importacao_siape/', dados)


def test_upload_identifica_e_importar_selecionados_conclui(cliente):
    resposta = _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    assert resposta.status_code == 302
    assert resposta.url.endswith(importacao.get_absolute_url())

    detalhe = cliente.get(importacao.get_absolute_url()).content.decode()
    assert 'bancos' in detalhe
    assert 'Layout mais próximo' in detalhe

    bancos = importacao.arquivos.get(layout='bancos')
    cliente.post(importacao.get_absolute_url(), {'arquivos': [bancos.pk]})

    progresso = cliente.get(f'{importacao.get_absolute_url()}progresso.json').json()
    assert progresso['situacao'] == 'concluida'
    assert {'id': bancos.pk, 'situacao': 'concluido'}.items() <= next(a for a in progresso['arquivos'] if a['id'] == bancos.pk).items()


def test_upload_de_arquivo_que_nao_e_zip_do_extrator_mostra_erro(cliente):
    resposta = _upload(cliente, 'extracao.zip', conteudo=b'nada')

    assert resposta.status_code == 200
    assert 'não é um zip válido' in resposta.content.decode()
    assert not ImportacaoSiape.objects.exists()


def test_interromper_libera_importacao_presa_para_uma_nova(cliente):
    _upload(cliente, 'a.zip')
    presa = ImportacaoSiape.objects.get()
    ImportacaoSiape.objects.filter(pk=presa.pk).update(situacao='executando')
    bancos = presa.arquivos.get(layout='bancos')
    estado_civil = presa.arquivos.get(layout='estado_civil')
    lote_executando = ImportacaoSiapeLote.objects.create(arquivo=bancos, numero=1, total_linhas=10, processadas=6, situacao='executando')
    lote_aguardando = ImportacaoSiapeLote.objects.create(arquivo=estado_civil, numero=2, total_linhas=10, situacao='aguardando')

    resposta = cliente.post(f'{presa.get_absolute_url()}interromper/', follow=True)

    presa.refresh_from_db()
    assert presa.situacao == 'falhou'
    assert presa.fim is not None
    assert 'interrompida' in resposta.content.decode()
    # os lotes presos não podem sobreviver à interrupção: senão o badge da tela segue mostrando
    # "em execução"/"na fila" muito depois de a importação ter falhado.
    lote_executando.refresh_from_db()
    lote_aguardando.refresh_from_db()
    assert (lote_executando.situacao, lote_aguardando.situacao) == ('falhou', 'pulado')
    assert lote_executando.fim is not None
    assert lote_aguardando.fim is not None
    assert 'interrompida' in lote_executando.motivo
    assert 'interrompida' in lote_aguardando.motivo
    assert arquivos_da_pasta(presa.pasta) == []

    _upload(cliente, 'b.zip')
    nova = ImportacaoSiape.objects.exclude(pk=presa.pk).get()
    bancos = nova.arquivos.get(layout='bancos')

    resposta = cliente.post(nova.get_absolute_url(), {'arquivos': [bancos.pk]}, follow=True)

    assert 'Já existe uma importação SIAPE em execução' not in resposta.content.decode()
    nova.refresh_from_db()
    assert nova.situacao in ('concluida', 'concluida_com_falhas')


def test_falha_ao_despachar_a_task_encerra_a_importacao_e_limpa_a_pasta(cliente):
    _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    bancos = importacao.arquivos.get(layout='bancos')

    with mock.patch('rh.tasks.executar_importacao_siape', side_effect=RuntimeError('broker indisponível')):
        resposta = cliente.post(importacao.get_absolute_url(), {'arquivos': [bancos.pk]}, follow=True)

    importacao.refresh_from_db()
    bancos.refresh_from_db()
    assert importacao.situacao == 'falhou'
    assert importacao.fim is not None
    assert bancos.situacao == 'falhou'  # estava 'aguardando' antes do despacho falhar
    assert arquivos_da_pasta(importacao.pasta) == []
    assert Log.objects.filter(app='rh', titulo='Importação de arquivos', texto__contains='broker indisponível').exists()
    assert 'Não foi possível iniciar a importação' in resposta.content.decode()


def test_ocorrencias_mostra_erros_primeiro_depois_as_mais_recentes(cliente):
    _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    bancos = importacao.arquivos.get(layout='bancos')
    ImportacaoSiapeOcorrencia.objects.create(arquivo=bancos, nivel='error', linha=1, mensagem='erro antigo')
    ImportacaoSiapeOcorrencia.objects.create(arquivo=bancos, nivel='warning', linha=2, mensagem='aviso um')
    ImportacaoSiapeOcorrencia.objects.create(arquivo=bancos, nivel='warning', linha=3, mensagem='aviso dois')

    conteudo = cliente.get(f'{importacao.get_absolute_url()}arquivo/{bancos.pk}/ocorrencias/').content.decode()

    assert conteudo.index('erro antigo') < conteudo.index('aviso dois') < conteudo.index('aviso um')


def test_ocorrencias_avisa_quando_a_lista_foi_cortada(cliente):
    _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    bancos = importacao.arquivos.get(layout='bancos')
    ImportacaoSiapeOcorrencia.objects.bulk_create(
        ImportacaoSiapeOcorrencia(arquivo=bancos, nivel='warning', linha=i, mensagem=f'aviso {i}') for i in range(2001)
    )

    conteudo = cliente.get(f'{importacao.get_absolute_url()}arquivo/{bancos.pk}/ocorrencias/').content.decode()

    assert 'Exibindo as 2000 primeiras de 2001 ocorrências' in conteudo


def test_nao_inicia_com_outra_importacao_em_execucao(cliente):
    _upload(cliente, 'a.zip')
    _upload(cliente, 'b.zip')
    primeira, segunda = ImportacaoSiape.objects.order_by('id')
    ImportacaoSiape.objects.filter(pk=primeira.pk).update(situacao='executando')

    resposta = cliente.post(segunda.get_absolute_url(), {'arquivos': []}, follow=True)

    assert 'Já existe uma importação SIAPE em execução' in resposta.content.decode()
    segunda.refresh_from_db()
    assert segunda.situacao == 'identificada'


@pytest.mark.usefixtures('lotes_pequenos')
def test_progresso_traz_lotes_do_layout_dividido_e_tela_renderiza_a_linha_de_lotes(cliente):
    _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    grupo = importacao.arquivos.get(layout='grupo_cargo_emprego')
    cargo = importacao.arquivos.get(layout='cargo_emprego')
    cliente.post(importacao.get_absolute_url(), {'arquivos': [grupo.pk, cargo.pk]})

    progresso = cliente.get(f'{importacao.get_absolute_url()}progresso.json').json()

    lotes = next(a for a in progresso['arquivos'] if a['id'] == cargo.pk)['lotes']
    assert len(lotes) > 1
    assert {lote['situacao'] for lote in lotes} == {'concluido'}
    assert progresso['workers'] == []

    detalhe = cliente.get(importacao.get_absolute_url()).content.decode()
    assert f'data-lotes-de="{cargo.pk}"' in detalhe


def test_progresso_traz_workers_a_partir_dos_lotes_em_execucao(cliente):
    importacao = ImportacaoSiape.objects.create(arquivo='a.zip', origem='tela', situacao='executando')
    cargo = importacao.arquivos.create(nome_ref='CAREMPR.REF', nome_txt='CAREMPR.TXT', layout='cargo_emprego', total_linhas=10, situacao='executando')
    rubrica = importacao.arquivos.create(nome_ref='RUBRICA.REF', nome_txt='RUBRICA.TXT', layout='rubrica', total_linhas=20, situacao='executando')
    ImportacaoSiapeLote.objects.create(arquivo=cargo, numero=1, total_linhas=5, processadas=5, situacao='concluido', worker='importacao_siape_0')
    ImportacaoSiapeLote.objects.create(arquivo=cargo, numero=2, total_linhas=5, processadas=3, situacao='executando', worker='importacao_siape_0')
    ImportacaoSiapeLote.objects.create(arquivo=rubrica, numero=1, total_linhas=10, processadas=4, situacao='executando', worker='importacao_siape_1')
    ImportacaoSiapeLote.objects.create(arquivo=rubrica, numero=2, total_linhas=10, processadas=0, situacao='aguardando')
    # ordenação numérica, não lexical: 'importacao_siape_10' viria antes de '..._9' num sort de string.
    dez = importacao.arquivos.create(nome_ref='X.REF', nome_txt='X.TXT', layout='servidor1', total_linhas=5, situacao='executando')
    ImportacaoSiapeLote.objects.create(arquivo=dez, numero=1, total_linhas=5, processadas=1, situacao='executando', worker='importacao_siape_10')
    nove = importacao.arquivos.create(nome_ref='Y.REF', nome_txt='Y.TXT', layout='servidor2', total_linhas=5, situacao='executando')
    ImportacaoSiapeLote.objects.create(arquivo=nove, numero=1, total_linhas=5, processadas=1, situacao='executando', worker='importacao_siape_9')

    progresso = cliente.get(f'{importacao.get_absolute_url()}progresso.json').json()

    workers = progresso['workers']
    assert [w['rotulo'] for w in workers] == ['W1', 'W2', 'W10', 'W11']
    assert (workers[0]['layout'], workers[0]['lote'], workers[0]['total_lotes']) == ('cargo_emprego', 2, 2)
    assert (workers[1]['layout'], workers[1]['lote'], workers[1]['total_lotes']) == ('rubrica', 1, 2)


def test_identificacao_oferece_importar_agora_e_agendar(cliente):
    resposta = _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    assert resposta.url.endswith(importacao.get_absolute_url())

    conteudo = cliente.get(importacao.get_absolute_url()).content.decode()

    assert 'value="importar"' in conteudo
    assert 'value="agendar"' in conteudo


def test_acao_agendar_grava_selecao_e_nao_roda_nada(cliente):
    _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    bancos = importacao.arquivos.get(layout='bancos')

    resposta = cliente.post(importacao.get_absolute_url(), {'acao': 'agendar', 'arquivos': [bancos.pk]}, follow=True)

    importacao.refresh_from_db()
    bancos.refresh_from_db()
    assert importacao.situacao == 'agendada'
    assert bancos.situacao == 'aguardando'
    assert bancos.selecionado
    assert importacao.arquivos.get(layout='estado_civil').situacao == 'ignorado'
    assert not ImportacaoSiapeLote.objects.filter(arquivo__importacao=importacao).exists()
    assert 'Agendada para a execução noturna' in resposta.content.decode()


def test_acao_cancelar_agendamento_volta_para_identificada(cliente):
    _upload(cliente, 'extracao.zip')
    importacao = ImportacaoSiape.objects.get()
    bancos = importacao.arquivos.get(layout='bancos')
    cliente.post(importacao.get_absolute_url(), {'acao': 'agendar', 'arquivos': [bancos.pk]})

    resposta = cliente.post(importacao.get_absolute_url(), {'acao': 'cancelar_agendamento'}, follow=True)

    importacao.refresh_from_db()
    bancos.refresh_from_db()
    assert importacao.situacao == 'identificada'
    assert bancos.situacao == 'pendente'
    assert bancos.selecionado  # mantém a última marcação do usuário
    assert 'Agendamento cancelado' in resposta.content.decode()


def test_upload_arquivos_extrator_redireciona_para_a_tela_nova(cliente):
    resposta = cliente.get('/rh/upload_arquivos_extrator/')

    assert resposta.status_code == 302
    assert resposta.url == '/rh/importacao_siape/'


def test_listagem_mostra_log_das_execucoes_e_as_colunas_novas(cliente):
    Log.objects.create(app='rh', titulo='Importação de arquivos', texto='Importação SIAPE #1 concluída.')
    importacao = ImportacaoSiape.objects.create(
        arquivo='a.zip',
        origem='tela',
        situacao='concluida',
        inicio=datetime(2026, 1, 1, 10, 0, 0),
        fim=datetime(2026, 1, 1, 10, 0, 5, 567891),
    )
    importacao.arquivos.create(
        nome_ref='BANCOS.REF',
        nome_txt='BANCOS.TXT',
        layout='bancos',
        selecionado=True,
        situacao='concluido',
        total_linhas=10,
        processadas=10,
        falhas=2,
    )

    conteudo = cliente.get('/rh/importacao_siape/').content.decode()

    assert 'Log das execuções' in conteudo
    assert 'Importação SIAPE #1 concluída.' in conteudo
    assert 'Duração' in conteudo
    assert 'Linhas importadas' in conteudo
    assert 'Falhas' in conteudo
    assert '0:00:05' in conteudo  # duração truncada para segundos inteiros
    assert '567891' not in conteudo  # sem microssegundos


def test_listagem_mostra_importacoes_e_log_do_mais_novo_para_o_mais_antigo(cliente):
    # a agregação (Sum) da listagem faz o Django ignorar o Meta.ordering: a ordem precisa ser explícita
    for arquivo in ('antiga.zip', 'meio.zip', 'nova.zip'):
        importacao = ImportacaoSiape.objects.create(arquivo=arquivo, origem='tela')
        importacao.arquivos.create(nome_ref='A.REF', nome_txt='A.TXT', layout='bancos', selecionado=True, processadas=1)
        Log.objects.create(app='rh', titulo='Importação de arquivos', texto=f'log de {arquivo}')

    conteudo = cliente.get('/rh/importacao_siape/').content.decode()

    assert conteudo.index('nova.zip') < conteudo.index('meio.zip') < conteudo.index('antiga.zip')
    assert conteudo.index('log de nova.zip') < conteudo.index('log de meio.zip') < conteudo.index('log de antiga.zip')


def test_listagem_calcula_falhas_e_avisos_sem_multiplicar_arquivos_por_ocorrencias(cliente):
    # 2 arquivos falhou + 1 pulado (falhas) e 1 ocorrência error (soma a falhas) + 2 warning (avisos):
    # falhas e avisos vêm de tabelas diferentes (arquivos/ocorrências) e não podem se multiplicar
    # entre si num join direto (um arquivo falho x duas ocorrências de outro arquivo, por exemplo).
    importacao = ImportacaoSiape.objects.create(arquivo='falhas_e_avisos.zip', origem='tela', situacao='falhou')
    falho1 = importacao.arquivos.create(nome_ref='A.REF', nome_txt='A.TXT', layout='bancos', selecionado=True, situacao='falhou')
    falho2 = importacao.arquivos.create(nome_ref='B.REF', nome_txt='B.TXT', layout='estado_civil', selecionado=True, situacao='falhou')
    importacao.arquivos.create(nome_ref='C.REF', nome_txt='C.TXT', layout='rubrica', selecionado=True, situacao='pulado')
    ImportacaoSiapeOcorrencia.objects.create(arquivo=falho1, nivel='error', linha=1, mensagem='erro')
    ImportacaoSiapeOcorrencia.objects.create(arquivo=falho2, nivel='warning', linha=1, mensagem='aviso um')
    ImportacaoSiapeOcorrencia.objects.create(arquivo=falho2, nivel='warning', linha=2, mensagem='aviso dois')

    resposta = cliente.get('/rh/importacao_siape/')

    assert 'Avisos' in resposta.content.decode()
    link = BeautifulSoup(resposta.content.decode(), 'html.parser').find('a', href=importacao.get_absolute_url())
    celulas = [celula.get_text(strip=True) for celula in link.find_parent('tr').find_all('td')]
    assert celulas[-2:] == ['4', '2']
