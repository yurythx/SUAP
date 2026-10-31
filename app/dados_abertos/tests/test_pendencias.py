"""Testes das pendências de dados abertos: indicadores do dashboard e notificação por responsabilidade."""

import datetime

import pytest
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile

from rh.tests.factories import ServidorFactory

from dados_abertos.enums import FormatoRecurso, Periodicidade, ResultadoAtualizacao, SituacaoLAI, SituacaoPDA
from dados_abertos.models import (
    AtualizacaoBaseDados,
    BaseDados,
    GrupoTrabalho,
    PDABaseDados,
    PlanoDadosAbertos,
    RecursoDados,
    ResponsavelGrupoTrabalho,
)
from dados_abertos.services import notificacao_service, pendencias_service

HOJE = datetime.date(2026, 6, 1)


@pytest.fixture
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def novo_servidor(db, sync_permissions):
    """Cria servidores sob demanda, no lugar do antigo fixture de cenário removido da base.

    Sob demanda porque cada servidor custa ~140 ms e ~220 queries, e nenhum teste daqui precisa
    de todos. O ``sync_permissions`` é exigido duas vezes: o ``save`` do Servidor busca grupos
    por nome, e ``_no_grupo`` também.
    """
    return ServidorFactory


@pytest.fixture
def cenario(novo_servidor, media_temporaria):
    """Um PDA vigente com três bases, cada uma exercitando uma pendência diferente.

    - ``devolvida``: sob responsabilidade do servidor A, prazo vencido e devolvida pelo LAI
    - ``sem_recurso``: nenhuma fonte cadastrada (pendência coletiva)
    - ``com_falha``: última execução da rotina falhou no download (pendência só do gestor)
    """
    servidor_a = novo_servidor()
    pda = PlanoDadosAbertos.objects.create(
        titulo='PDA vigente',
        vigencia_inicio=datetime.date(2026, 1, 1),
        vigencia_fim=datetime.date(2027, 12, 31),
        situacao=SituacaoPDA.EM_EXECUCAO,
    )

    devolvida = BaseDados.objects.create(nome='contratos', titulo='Contratos')
    RecursoDados.objects.create(
        dataset=devolvida,
        nome='Contratos',
        formato=FormatoRecurso.JSON,
        url='https://suap.br/api/contrato/contratos/?ano=2026',
        arquivo=ContentFile(b'[]', name='contratos.json'),
    )
    rel_devolvida = PDABaseDados.objects.create(
        pda=pda,
        base_dados=devolvida,
        responsavel_abertura=servidor_a,
        meta_prazo_abertura=datetime.date(2026, 3, 1),
        frequencia_atualizacao=Periodicidade.MENSAL,
    )
    PDABaseDados.objects.filter(pk=rel_devolvida.pk).update(situacao_lai=SituacaoLAI.DEVOLVIDO)

    sem_recurso = BaseDados.objects.create(nome='inventario', titulo='Inventário')
    PDABaseDados.objects.create(pda=pda, base_dados=sem_recurso, responsavel_abertura=servidor_a, meta_prazo_abertura=datetime.date(2027, 1, 1))

    com_falha = BaseDados.objects.create(nome='servidores', titulo='Servidores')
    RecursoDados.objects.create(
        dataset=com_falha,
        nome='Servidores',
        formato=FormatoRecurso.JSON,
        url='https://suap.br/api/rh/servidores/',
        arquivo=ContentFile(b'[]', name='servidores.json'),
    )
    # Sem responsável nem prazo: alimenta a pendência de cronograma incompleto.
    PDABaseDados.objects.create(pda=pda, base_dados=com_falha)
    AtualizacaoBaseDados.objects.create(base_dados=com_falha, resultado=ResultadoAtualizacao.FALHA_DOWNLOAD, detalhe='404')

    return {'pda': pda, 'devolvida': devolvida, 'sem_recurso': sem_recurso, 'com_falha': com_falha, 'servidor_a': servidor_a}


def _no_grupo(servidor, nome_grupo):
    grupo = Group.objects.get(name=nome_grupo)
    servidor.get_user().groups.add(grupo)
    return servidor.get_vinculo()


def _chaves(pendencias):
    return {p.chave for p in pendencias}


def test_responsavel_pela_abertura_ve_o_que_e_dele(cenario):
    """Prazo vencido e devolução do LAI são cobrança direta de quem responde pela base."""
    vinculo = cenario['servidor_a'].get_vinculo()

    chaves = _chaves(pendencias_service.pessoais(vinculo, hoje=HOJE))

    assert 'prazo_vencido' in chaves
    assert 'devolvidas_lai' in chaves


def test_responsavel_lai_ve_a_fila_de_deliberacao(cenario, novo_servidor):
    """Quem delibera vê os datasets em análise; quem não delibera, não."""
    PDABaseDados.objects.filter(base_dados=cenario['devolvida']).update(situacao_lai=SituacaoLAI.EM_ANALISE)
    vinculo_lai = _no_grupo(novo_servidor(), 'Responsável LAI')

    assert 'lai_a_deliberar' in _chaves(pendencias_service.pessoais(vinculo_lai, hoje=HOJE))
    assert 'lai_a_deliberar' not in _chaves(pendencias_service.pessoais(cenario['servidor_a'].get_vinculo(), hoje=HOJE))


def test_pda_encerrado_nao_gera_pendencia(cenario):
    """Prazo vencido em plano encerrado é água passada — cobrar isso seria ruído permanente."""
    PlanoDadosAbertos.objects.filter(pk=cenario['pda'].pk).update(situacao=SituacaoPDA.ENCERRADO)

    assert pendencias_service.pessoais(cenario['servidor_a'].get_vinculo(), hoje=HOJE) == []


def test_coletivas_reunem_o_estado_do_plano(cenario):
    """O agregado do plano: falha da rotina, base sem recurso e cronograma incompleto."""
    chaves = _chaves(pendencias_service.coletivas(hoje=HOJE))

    assert chaves == {'falha_rotina', 'sem_recurso', 'cronograma_incompleto'}


def test_indicadores_seguem_o_contrato_do_dashboard(cenario):
    """O template ``atribuidos.html`` lê titulo/subtitulo/qtd/url de cada dict."""
    indicadores = pendencias_service.como_indicadores(pendencias_service.coletivas(hoje=HOJE))

    assert indicadores
    assert all({'titulo', 'subtitulo', 'qtd', 'url'} <= set(indicador) for indicador in indicadores)


@pytest.fixture
def envios(monkeypatch):
    """Captura as chamadas a ``send_notification`` como (assunto, mensagem, vínculos)."""
    registro = []

    def fake(assunto, mensagem, de, vinculos, **kwargs):
        registro.append((assunto, mensagem, list(vinculos)))

    monkeypatch.setattr(notificacao_service, 'send_notification', fake)
    return registro


def _mensagem_de(envios, vinculo):
    """Mensagem que chegou a este vínculo (assume uma só — a dedup é testada à parte)."""
    recebidas = [mensagem for _, mensagem, vinculos in envios if any(v.pk == vinculo.pk for v in vinculos)]
    assert len(recebidas) == 1, f'esperava uma notificação, vieram {len(recebidas)}'
    return recebidas[0]


def test_grupo_de_trabalho_nao_recebe_falha_tecnica(cenario, novo_servidor, envios):
    """URL de origem fora do ar é assunto do gestor; o grupo de trabalho recebe só o resto."""
    vinculo_gestor = _no_grupo(novo_servidor(), 'Gestor de Dados Abertos Sistêmico')
    vinculo_gt = _no_grupo(novo_servidor(), 'Membros do Grupo de Trabalho')

    notificacao_service.notificar(hoje=HOJE)

    falha = 'falha na última atualização automática'
    assert falha in _mensagem_de(envios, vinculo_gestor)
    mensagem_gt = _mensagem_de(envios, vinculo_gt)
    assert falha not in mensagem_gt
    # E o que é dele continua chegando.
    assert 'sem recurso cadastrado' in mensagem_gt


def test_pessoa_no_grupo_e_no_gt_do_pda_recebe_uma_vez(cenario, novo_servidor, envios):
    """Estar nas duas origens do grupo de trabalho não duplica a notificação."""
    vinculo_gt = _no_grupo(novo_servidor(), 'Membros do Grupo de Trabalho')
    grupo = GrupoTrabalho.objects.create(pda=cenario['pda'], descricao='GT do PDA')
    ResponsavelGrupoTrabalho.objects.create(grupo_trabalho=grupo, responsavel=vinculo_gt)

    notificacao_service.notificar(hoje=HOJE)

    recebimentos = [v for _, _, vinculos in envios for v in vinculos if v.pk == vinculo_gt.pk]
    assert len(recebimentos) == 1


def test_sem_pendencia_nao_notifica(novo_servidor, envios):
    """Nenhum PDA, nenhuma base: ninguém recebe nada."""
    _no_grupo(novo_servidor(), 'Gestor de Dados Abertos Sistêmico')

    notificacao_service.notificar(hoje=HOJE)

    assert envios == []


def test_dry_run_nao_envia(cenario, novo_servidor, envios):
    """A simulação mostra o que sairia sem tocar em notificação nenhuma."""
    _no_grupo(novo_servidor(), 'Gestor de Dados Abertos Sistêmico')

    resumo = notificacao_service.notificar(hoje=HOJE, dry_run=True)

    assert envios == []
    assert resumo.coletivas > 0


def test_o_command_de_notificacao_executa(cenario, novo_servidor, envios, capsys):
    """O agendamento do Celery Beat chama o command; ele delega ao service e resume o que saiu."""
    from django.core.management import call_command

    _no_grupo(novo_servidor(), 'Gestor de Dados Abertos Sistêmico')

    call_command('notificar_pendencias_dados_abertos')

    assert 'Coletivas: 1' in capsys.readouterr().out
    assert envios


def test_receivers_do_index_respondem_ao_contrato(cenario):
    """Os receivers rodam no index de todo usuário.

    ``djtools.layout.connect_signal`` os envolve em ``@silenciar(return_on_error=[])``: um erro
    aqui não quebra o index, some. Por isso a checagem é por teste, e pela assinatura real do
    receiver registrado — ``(sender, request, **kwargs)``.
    """
    from types import SimpleNamespace

    from dados_abertos import views

    servidor = cenario['servidor_a']
    request = SimpleNamespace(user=servidor.get_user())

    meus = views.index_atribuidos_a_mim(sender=None, request=request)
    coletivos = views.index_atribuidos_a_meus_grupos(sender=None, request=request)

    assert any(indicador['subtitulo'] == 'com prazo de abertura vencido' for indicador in meus)
    # Sem a permissão de gestor, as coletivas não custam nem uma consulta.
    assert coletivos == []
