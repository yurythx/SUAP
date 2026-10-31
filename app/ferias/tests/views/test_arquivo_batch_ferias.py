"""Testes da geração do arquivo batch de férias (admin de ``Ferias``)."""

from datetime import date

import pytest
from django.test import Client

from comum.models import Configuracao
from comum.tests.factories import AnoFactory
from ferias.models import Ferias
from ferias.tests.factories import FeriasFactory
from rh.tests.factories import ServidorFactory

# Leiaute posicional do arquivo batch de férias do SIAPE, com as datas e opções dos FeriasFactory abaixo.
JUSTIFICATIVA = 'Ferias marcadas para o proximo exercicio em razao de necessidade de servico do setor de trabalho do servidor.'
ARQUIVO_ESPERADO = (
    # Cabeçalho: 0 + código da instituição + zeros + mês/ano + IF<UF> + PROG-FERIAS.
    # Sem freezegun: congelar o relógio antes do 1º request quebra o schema do django-ninja (FakeDate).
    f'026435{"0" * 9}{date.today():%m%Y}IFRN{" " * 38}PROG-FERIAS{" " * 6}\n'
    # 1 + instituição + matrícula + 0 + comando 4 + exercício + (início, fim, N, 70%, gratificação) x 3 períodos.
    # Servidor 4 (exercício mais novo, vem primeiro): só o período 1, sem opções nem justificativa.
    f'12643544444440420270102202710022027NNN{"0" * 16}NNN{"0" * 16}NNN    {" " * 240}\n'
    # Servidor 1: 70% nos períodos 1 e 2, gratificação no 2, período 1 invade o exercício seguinte.
    f'12643511111110420262012202605012027NSN1001202715012027NSS{"0" * 16}NNN    {JUSTIFICATIVA}\n'
    # Servidor 2: não invade o exercício seguinte, então sai sem a justificativa da linha anterior (#17461).
    f'12643522222220420250103202510032025NSN0106202510062025NSN0107202510072025NSS    {" " * 240}\n'
    # Rodapé: 9 + instituição + noves + quantidade de linhas.
    f'926435{"9" * 9}0000003{" " * 58}\n'
)


@pytest.mark.django_db
def test_sem_uf_configurada_pede_configuracao_em_vez_de_500(admin_client: Client) -> None:
    Configuracao.objects.filter(app='comum', chave='instituicao_estado').delete()
    Configuracao.clear_cache()

    resposta = admin_client.get('/admin/ferias/ferias/gerar_arquivo_batch_ferias/')

    assert resposta.status_code == 200
    assert 'Defina UF e o código da instituição' in resposta.content.decode()


def configurar_instituicao() -> None:
    for chave, valor in [('instituicao_estado', 'rn'), ('instituicao_identificador', '26435')]:
        Configuracao.objects.update_or_create(app='comum', chave=chave, defaults={'valor': valor})
    Configuracao.clear_cache()


@pytest.mark.django_db
@pytest.mark.parametrize(
    'periodo2',
    [
        pytest.param((date(2026, 6, 1), date(2026, 6, 10)), id='periodo2-no-exercicio'),
        pytest.param((None, None), id='sem-periodo2'),
    ],
)
def test_periodo3_que_invade_o_exercicio_seguinte_leva_justificativa(
    admin_client: Client, sync_permissions: None, periodo2: tuple[date | None, date | None]
) -> None:
    configurar_instituicao()
    FeriasFactory(
        servidor=ServidorFactory(matricula='5555555'),
        ano=AnoFactory(ano=2026),
        data_inicio_periodo1=date(2026, 3, 1),
        data_fim_periodo1=date(2026, 3, 10),
        data_inicio_periodo2=periodo2[0],
        data_fim_periodo2=periodo2[1],
        data_inicio_periodo3=date(2026, 12, 28),
        data_fim_periodo3=date(2027, 1, 6),
    )

    resposta = admin_client.get('/admin/ferias/ferias/gerar_arquivo_batch_ferias/')

    assert resposta.status_code == 200
    linha_servidor = resposta.content.decode().splitlines()[1]
    assert linha_servidor.endswith(f'2812202606012027NNN    {JUSTIFICATIVA}')


@pytest.mark.django_db
def test_arquivo_batch_das_ferias_validadas(admin_client: Client, sync_permissions: None) -> None:
    configurar_instituicao()
    FeriasFactory(
        servidor=ServidorFactory(matricula='1111111'),
        ano=AnoFactory(ano=2026),
        data_inicio_periodo1=date(2026, 12, 20),
        data_fim_periodo1=date(2027, 1, 5),
        data_inicio_periodo2=date(2027, 1, 10),
        data_fim_periodo2=date(2027, 1, 15),
        setenta_porcento=5,
        gratificacao_natalina=2,
    )
    FeriasFactory(
        servidor=ServidorFactory(matricula='2222222'),
        ano=AnoFactory(ano=2025),
        data_inicio_periodo1=date(2025, 3, 1),
        data_fim_periodo1=date(2025, 3, 10),
        data_inicio_periodo2=date(2025, 6, 1),
        data_fim_periodo2=date(2025, 6, 10),
        data_inicio_periodo3=date(2025, 7, 1),
        data_fim_periodo3=date(2025, 7, 10),
        setenta_porcento=7,
        gratificacao_natalina=3,
    )
    FeriasFactory(
        servidor=ServidorFactory(matricula='4444444'),
        ano=AnoFactory(ano=2027),
        data_inicio_periodo1=date(2027, 2, 1),
        data_fim_periodo1=date(2027, 2, 10),
    )
    FeriasFactory(servidor=ServidorFactory(matricula='3333333'), ano=AnoFactory(ano=2024), validado=Ferias.PENDENTE)

    resposta = admin_client.get('/admin/ferias/ferias/gerar_arquivo_batch_ferias/')

    assert resposta['Content-Disposition'] == 'attachment; filename=ferias.txt'
    assert resposta.content.decode() == ARQUIVO_ESPERADO
