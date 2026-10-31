from datetime import date, timedelta

import pytest
from django.core.management import CommandError
from django.db import connection
from django.db.models import SET_NULL
from django.test.utils import CaptureQueriesContext

from comum.models import APIExterna, Comentario, ContatoEmergencia, Ocupacao, OcupacaoPrestador, Pais, PessoaEndereco, PessoaTelefone, Vinculo
from comum.tests.factories import PrestadorServicoFactory, UserFactory
from edu.models import Pais as PaisEdu
from edu.models import SituacaoMatricula
from edu.tests.factories import AlunoFactory, SituacaoMatriculaFactory
from rh.deduplicacao.aplicacao import _apagar_perdedoras, _aplicar_higiene, _preencher_sobreviventes, aplicar
from rh.deduplicacao.plano import planejar
from rh.models import DeduplicacaoPessoa as D
from rh.models import PessoaExterna, PessoaFisica, PessoaInfoComplementar
from rh.tests.factories import PessoaFisicaFactory, PessoaJuridicaFactory, ServidorFactory, SetorFactory

pytestmark = pytest.mark.usefixtures('sem_unicidade_pessoa', 'pessoas_com_relacionamento')
CPF = '529.982.247-25'


def _acoes(pk: int) -> set[str]:
    return set(D.objects.filter(pf_id=pk).values_list('acao', flat=True))


def _legada(**campos: object) -> PessoaFisica:
    """PF como as da base legada: grava direto, sem passar pelo save()."""
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(**campos)
    return PessoaFisica.objects.get(pk=pessoa.pk)


def test_planejar_nao_escreve_em_pessoa() -> None:
    a, b = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)

    planejar()

    assert PessoaFisica.objects.filter(pk__in=[a.pk, b.pk]).count() == 2
    assert D.objects.get(pf_id=a.pk, acao=D.MESCLADA).sobrevivente_id == b.pk


def test_nascimento_divergente_separa_com_documento_conflito() -> None:
    separada = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 1, 1))  # sem papel, vence o maior id

    planejar()

    linha = D.objects.get(pf_id=separada.pk, acao=D.SEPARADA)
    assert linha.documento == f'CONFLITO-{separada.pk}-{CPF}'
    assert (linha.campo, linha.valor_original) == ('cpf', CPF)


def test_sem_documento_e_cpf_invalido_viram_sinteticos() -> None:
    sem = _legada(cpf='___.___.___-__', documento_identificador=None)
    invalido = _legada(cpf='529.982.247-24')

    planejar()

    assert D.objects.get(pf_id=sem.pk, acao=D.SINTETICO).documento == f'SEMDOC-{sem.pk}'
    assert {D.CPF_ANULADO, D.SINTETICO} <= _acoes(invalido.pk)
    assert D.objects.get(pf_id=invalido.pk, acao=D.SINTETICO).documento == f'INVALIDO-{invalido.pk}-52998224724'


def test_um_para_um_colidindo_separa_o_grupo() -> None:
    from comum.models import ContatoEmergencia

    a, b = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_um_contato ON comum_contatoemergencia (pessoa_fisica_id)')
    for pessoa in (a, b):
        ContatoEmergencia.objects.create(pessoa_fisica=pessoa, nome_contato='Mãe', telefone='84999999999')

    planejar()

    assert D.objects.get(pf_id=a.pk, acao=D.SEPARADA).motivo.startswith('unicidade em comum_contatoemergencia')


def test_nascimento_da_maioria_fica_com_o_documento_e_as_separadas_se_unem(sync_permissions: None) -> None:
    """Caso do suap_dev (CPF de servidor e alunos antigos, 17/09): um prestador ativo com 19/09 não leva o CPF; as de 17/09 viram uma só."""
    maioria = [PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 9, 17)) for _ in range(3)]
    sem_nascimento = PessoaFisicaFactory(cpf=CPF, nascimento_data=None)
    minoria = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 9, 19))
    PrestadorServicoFactory(pessoa_fisica=minoria)  # ativo: pela regra antiga, seria a sobrevivente

    _deduplicar()

    assert planejar() == {}
    restantes = PessoaFisica.objects.filter(pk__in=[*(p.pk for p in maioria), sem_nascimento.pk, minoria.pk])
    assert {(p.cpf, p.nascimento_data) for p in restantes} == {(CPF, date(1991, 9, 17)), (None, date(1991, 9, 19))}
    assert PessoaFisica.objects.get(pk=minoria.pk).documento_identificador == f'CONFLITO-{minoria.pk}-{CPF}'


def test_servidor_ativo_mantem_o_documento_mesmo_em_minoria(sync_permissions: None) -> None:
    """O nascimento do servidor ativo vem do SIAPE: ele fica com o CPF, e as divergentes de mesmo nascimento se unem numa CONFLITO-."""
    divergentes = [PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 9, 17)) for _ in range(2)]
    servidor = ServidorFactory(pessoa_fisica=PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 9, 19)))

    _deduplicar()

    assert planejar() == {}
    assert PessoaFisica.objects.get(pk=servidor.pessoa_fisica_id).cpf == CPF
    unidas = PessoaFisica.objects.filter(pk__in=[p.pk for p in divergentes])
    assert [(p.cpf, p.documento_identificador) for p in unidas] == [(None, f'CONFLITO-{max(p.pk for p in divergentes)}-{CPF}')]


def test_conflitos_ja_gravados_de_mesmo_documento_e_nascimento_se_unem() -> None:
    """Separadas pela regra antiga (uma CONFLITO- por PF) são unidas por documento original e nascimento."""
    a = _legada(cpf=None, nascimento_data=date(1991, 9, 17), documento_identificador=None)
    b = _legada(cpf=None, nascimento_data=date(1991, 9, 17), documento_identificador=None)
    outra = _legada(cpf=None, nascimento_data=date(1980, 1, 1), documento_identificador=None)
    for pessoa in (a, b, outra):
        PessoaFisica.objects.filter(pk=pessoa.pk).update(documento_identificador=f'CONFLITO-{pessoa.pk}-{CPF}')

    _deduplicar()

    assert planejar() == {}
    assert not PessoaFisica.objects.filter(pk=a.pk).exists()
    assert PessoaFisica.objects.get(pk=b.pk).documento_identificador == f'CONFLITO-{b.pk}-{CPF}'
    assert PessoaFisica.objects.get(pk=outra.pk).documento_identificador == f'CONFLITO-{outra.pk}-{CPF}'


def test_conflito_volta_para_a_dona_do_documento_quando_o_nascimento_e_corrigido(sync_permissions: None) -> None:
    """Corrigido o nascimento que causou a separação, a CONFLITO- volta para a dona do CPF (que fica com ele); a divergente, não."""
    dona = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 9, 17))
    PrestadorServicoFactory(pessoa_fisica=dona)
    separada = _legada(cpf=None, nascimento_data=date(1991, 9, 17), documento_identificador=None)
    divergente = _legada(cpf=None, nascimento_data=date(1980, 1, 1), documento_identificador=None)
    for pessoa in (separada, divergente):
        PessoaFisica.objects.filter(pk=pessoa.pk).update(documento_identificador=f'CONFLITO-{pessoa.pk}-{CPF}')

    _deduplicar()

    assert planejar() == {}
    assert not PessoaFisica.objects.filter(pk=separada.pk).exists()
    assert PessoaFisica.objects.get(pk=dona.pk).documento_identificador == CPF
    assert PessoaFisica.objects.get(pk=divergente.pk).documento_identificador == f'CONFLITO-{divergente.pk}-{CPF}'


def test_unidas_que_colidem_em_um_para_um_seguem_separadas() -> None:
    """A colisão desfaz a união sem separar de novo: a CONFLITO- já gravada não perde o passaporte."""
    from comum.models import ContatoEmergencia

    pessoas = [_legada(cpf=None, passaporte='AB123456', nascimento_data=date(1991, 9, 17), documento_identificador=None) for _ in range(2)]
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_um_contato ON comum_contatoemergencia (pessoa_fisica_id)')
    for pessoa in pessoas:
        PessoaFisica.objects.filter(pk=pessoa.pk).update(documento_identificador=f'CONFLITO-{pessoa.pk}-{CPF}')
        ContatoEmergencia.objects.create(pessoa_fisica=pessoa, nome_contato='Mãe', telefone='84999999999')

    assert planejar() == {}
    assert [p.passaporte for p in PessoaFisica.objects.filter(pk__in=[p.pk for p in pessoas])] == ['AB123456', 'AB123456']


def test_passaporte_repetido_entre_pessoas_diferentes_fica_com_a_prioritaria() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    a = PessoaFisicaFactory(cpf=CPF, passaporte='AB123456', pais_origem=argentina)
    b = PessoaFisicaFactory(cpf='390.533.447-05', passaporte='AB123456', pais_origem=argentina)

    planejar()

    assert D.objects.get(pf_id=a.pk, acao=D.PASSAPORTE_ANULADO).valor_original == 'AB123456'
    assert D.PASSAPORTE_ANULADO not in _acoes(b.pk)


def test_mesmo_passaporte_em_paises_diferentes_nao_agrupa() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    chile = Pais.objects.create(codigo='158', nome='CHILE', iso_alfa3='CHL')
    a = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    b = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=chile)

    planejar()

    assert not D.objects.filter(pf_id__in=[a.pk, b.pk], acao__in=[D.MESCLADA, D.SEPARADA, D.PASSAPORTE_ANULADO]).exists()


def test_mesmo_passaporte_nos_dois_codigos_da_suica_agrupa() -> None:
    suica_150 = Pais.objects.create(codigo='150', nome='SUICA', iso_alfa3='CHE')
    suica_236 = Pais.objects.create(codigo='236', nome='SUICA', iso_alfa3='CHE')
    a = _legada(cpf=None, passaporte='X1234567', pais_origem=suica_150)
    b = _legada(cpf=None, passaporte='X1234567', pais_origem=suica_236)

    planejar()

    assert D.objects.filter(acao=D.MESCLADA, pf_id__in=[a.pk, b.pk]).count() == 1


def test_legada_com_pais_sem_iso_recebe_sintetico() -> None:
    sem_iso = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')
    pessoa = _legada(cpf=None, passaporte='AB123456', pais_origem=sem_iso, documento_identificador='AB123456/005')

    planejar()

    assert D.objects.get(pf_id=pessoa.pk, acao=D.SINTETICO).documento == f'SEMDOC-{pessoa.pk}'


def test_passaporte_repetido_em_pais_sem_iso_e_anulado_e_libera_a_trava() -> None:
    from rh.deduplicacao.verificacao import pendencias

    sem_iso = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')
    a = _legada(cpf=None, passaporte='AB123456', pais_origem=sem_iso)
    b = _legada(cpf=None, passaporte='AB123456', pais_origem=sem_iso)

    planejar()
    aplicar()

    assert D.objects.get(pf_id=a.pk, acao=D.PASSAPORTE_ANULADO).valor_original == 'AB123456'
    assert D.PASSAPORTE_ANULADO not in _acoes(b.pk)
    assert D.MESCLADA not in _acoes(a.pk) | _acoes(b.pk)  # sem ISO, o passaporte não é documento: não mescla
    planejar()  # o portão da 4.0.0: o replanejar não deixa nada pendente
    assert not D.objects.filter(pf_id__in=[a.pk, b.pk], aplicado_em__isnull=True).exists()
    with connection.cursor() as cursor:
        assert pendencias(cursor)['passaporte_repetido'] == 0


def test_sem_cpf_aluno_brasileiro_ganha_brasil() -> None:
    from comum.models import Pais
    from edu.tests.factories import AlunoFactory

    brasil = Pais.objects.create(codigo='024', nome='BRASIL')
    sem_cpf = _legada(cpf=None, documento_identificador=None)
    AlunoFactory(pessoa_fisica=sem_cpf, nacionalidade='Brasileira')
    com_cpf = PessoaFisicaFactory()
    AlunoFactory(pessoa_fisica=com_cpf, nacionalidade='Brasileira')

    planejar()

    assert D.objects.get(pf_id=sem_cpf.pk, acao=D.PAIS_PREENCHIDO).documento == str(brasil.pk)
    assert D.PAIS_PREENCHIDO not in _acoes(com_cpf.pk)


def test_fk_desconhecida_aborta() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE tmp_fantasma (id serial PRIMARY KEY, pf integer REFERENCES pessoa_fisica (pessoa_ptr_id))')

    with pytest.raises(CommandError, match=r'tmp_fantasma\.pf') as erro:
        planejar()

    # a mensagem traz a recomendação pronta para o DBA: arquivar e apagar a tabela, ou só tirar a FK
    mensagem = str(erro.value)
    assert 'pg_dump -Fc -t tmp_fantasma -f tabelas-fora-de-migration.dump' in mensagem
    assert 'DROP TABLE tmp_fantasma;' in mensagem
    assert 'ALTER TABLE tmp_fantasma DROP CONSTRAINT tmp_fantasma_pf_fkey;' in mensagem


def test_replanejar_descarta_so_o_que_nao_foi_aplicado() -> None:
    PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    aplicada = D.objects.create(pf_id=1, acao=D.MESCLADA, sobrevivente_id=2, aplicado_em='2026-01-01T00:00:00Z')

    planejar()
    planejar()

    assert D.objects.filter(pk=aplicada.pk).exists()
    assert D.objects.filter(acao=D.MESCLADA, aplicado_em__isnull=True).count() == 1


def test_sintetico_ja_gravado_sobrevive_a_novo_planejar() -> None:
    separada = _legada(cpf=None, documento_identificador=f'CONFLITO-1-{CPF}')

    planejar()

    assert D.SINTETICO not in _acoes(separada.pk)


def test_vencedora_sem_nascimento_usa_o_da_mais_prioritaria_com_data() -> None:
    a = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    b = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 1, 1))
    vencedora = PessoaFisicaFactory(cpf=CPF)  # sem papel, vence o maior id

    planejar()

    assert D.objects.get(pf_id=a.pk, acao=D.SEPARADA).motivo == f'nascimento 1990-01-01 ≠ 1991-01-01 da PF {b.pk}'
    assert D.objects.get(pf_id=b.pk, acao=D.MESCLADA).sobrevivente_id == vencedora.pk


def test_senha_divergente_e_auditada_sem_o_valor() -> None:
    perdedora = PessoaFisicaFactory(cpf=CPF, senha_ponto='segredo-1')
    PessoaFisicaFactory(cpf=CPF, senha_ponto='segredo-2')

    planejar()

    linha = D.objects.get(pf_id=perdedora.pk, acao=D.CAMPO_DESCARTADO, campo='senha_ponto')
    assert (linha.valor_original, linha.motivo) == ('', 'valor omitido (biometria/senha)')


def test_separada_por_passaporte_nao_recebe_de_volta_o_passaporte_do_aluno() -> None:
    """A separação vale até alguém corrigir o documento: copiar o passaporte do aluno de volta recriaria o par e separaria de novo
    a cada rodada (o planejar nunca convergiria e a trava da 4.0.0 não liberaria)."""
    colombia = Pais.objects.create(codigo='040', nome='COLOMBIA', iso_alfa3='COL')
    a = _legada(cpf=None, passaporte='AW207929', pais_origem=colombia, nascimento_data=date(1990, 1, 1), documento_identificador=None)
    b = _legada(cpf=None, passaporte='AW207929', pais_origem=colombia, nascimento_data=date(1985, 5, 5), documento_identificador=None)
    AlunoFactory(pessoa_fisica=a, passaporte='AW207929')
    AlunoFactory(pessoa_fisica=b, passaporte='AW207929')

    planejar()
    aplicar()
    segunda = planejar()

    assert segunda == {}
    assert D.objects.filter(aplicado_em__isnull=True).count() == 0


def test_passaporte_com_pontuacao_vira_a_chave_e_converge() -> None:
    """O passaporte vira só letras e dígitos e a chave, ISO + hífen + número (o login do estrangeiro sem CPF)."""
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    pontuado = _legada(cpf=None, passaporte='ab-123.456', pais_origem=argentina, documento_identificador=None)
    limpo = _legada(cpf=None, passaporte='AB123456', pais_origem=argentina, documento_identificador=None)

    planejar()
    aplicar()

    sobrevivente = PessoaFisica.objects.get(pk__in=[pontuado.pk, limpo.pk])
    assert (sobrevivente.passaporte, sobrevivente.documento_identificador) == ('AB123456', 'ARG-AB123456')
    assert planejar() == {}


def test_mescla_nao_deixa_telefone_nem_endereco_repetido() -> None:
    """Cada cópia trazia os seus contatos: a sobrevivente fica com um de cada, e o contato diferente fica."""
    pessoas = [PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)]
    for pessoa in pessoas:
        PessoaTelefone.objects.create(pessoa=pessoa, numero='(84) 3091-7558')
        PessoaTelefone.objects.create(pessoa=pessoa, numero='8430917558')
        PessoaEndereco.objects.create(pessoa=pessoa, logradouro='Rua A', numero='10', cep='59000-000')
    PessoaTelefone.objects.create(pessoa=pessoas[0], numero='(84) 99918-1040')

    resumo = _deduplicar()

    sobrevivente = PessoaFisica.objects.get(cpf=CPF)
    assert sorted(PessoaTelefone.objects.filter(pessoa=sobrevivente).values_list('numero', flat=True)) == ['(84) 3091-7558', '(84) 99918-1040']
    assert PessoaEndereco.objects.filter(pessoa=sobrevivente).count() == 1
    assert resumo['contatos'] == 4
    assert aplicar()['contatos'] == 0


def test_aplicar_recalcula_a_busca_de_quem_tem_passaporte() -> None:
    """A busca inclui o passaporte com o país desde a 3.21.0; a das PFs gravadas antes é recalculada no aplicar."""
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    pessoa = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    PessoaFisica.objects.filter(pk=pessoa.pk).update(search_fields_optimized='busca antiga')

    assert aplicar()['busca'] == 1
    assert 'ARG-AB123456' in PessoaFisica.objects.get(pk=pessoa.pk).search_fields_optimized
    assert aplicar()['busca'] == 0
    # o banco devolve os vínculos sem ordem fixa: a ordem dos usernames não muda a busca (senão o aplicar regravaria sempre)
    assert pessoa._get_search_fields_optimized_content_to_save(['b', 'a']) == pessoa._get_search_fields_optimized_content_to_save(['a', 'b'])


def test_passaporte_do_aluno_so_e_copiado_se_valido() -> None:
    brasil = Pais.objects.create(codigo='024', nome='BRASIL')
    com_invalido = _legada(cpf=None, passaporte=None, pais_origem=brasil, documento_identificador=None)
    AlunoFactory(pessoa_fisica=com_invalido, passaporte='AAAAAA')
    trocado = _legada(cpf=None, passaporte='X1', pais_origem=brasil, documento_identificador=None)
    AlunoFactory(pessoa_fisica=trocado, passaporte='AB123456')

    planejar()

    assert not {D.PASSAPORTE_PREENCHIDO, D.PASSAPORTE_ANULADO} & _acoes(com_invalido.pk)
    assert D.PASSAPORTE_ANULADO not in _acoes(trocado.pk)
    linha = D.objects.get(pf_id=trocado.pk, acao=D.PASSAPORTE_PREENCHIDO)
    assert (linha.documento, linha.valor_original) == ('AB123456', 'X1')


def test_pais_vem_so_do_aluno_mais_recente() -> None:
    Pais.objects.create(codigo='024', nome='BRASIL')
    sem_cpf = _legada(cpf=None, documento_identificador=None)
    AlunoFactory(pessoa_fisica=sem_cpf, nacionalidade='Brasileira')
    AlunoFactory(pessoa_fisica=sem_cpf, nacionalidade='Estrangeira', pais_origem=PaisEdu.objects.create(sigla='AT', nome='Atlântida', codigo='900'))

    planejar()

    assert D.PAIS_PREENCHIDO not in _acoes(sem_cpf.pk)


def test_aluno_estrangeiro_converte_o_pais_pelo_nome_e_nao_pelo_codigo() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    Pais.objects.create(codigo='063', nome='CHILE')
    sem_cpf = _legada(cpf=None, documento_identificador=None)
    AlunoFactory(pessoa_fisica=sem_cpf, nacionalidade='Estrangeira', pais_origem=PaisEdu.objects.create(sigla='AR', nome='Argentina', codigo='063'))

    planejar()

    assert D.objects.get(pf_id=sem_cpf.pk, acao=D.PAIS_PREENCHIDO).documento == str(argentina.pk)


def test_aluno_estrangeiro_sem_nome_igual_converte_o_pais_pela_sigla_alfa3() -> None:
    """Caso da suap_dev: "República Árabe Do Egito" no edu, "EGITO" no SIAPE; a sigla EGY é a mesma. Com territórios no mesmo
    alfa-3, fica o país de menor código do SIAPE (o do Estado)."""
    egito = Pais.objects.create(codigo='050', nome='EGITO', iso_alfa3='EGY')
    eua = Pais.objects.create(codigo='055', nome='ESTADOS UNIDOS', iso_alfa3='USA')
    Pais.objects.create(codigo='210', nome='PORTO RICO', iso_alfa3='USA')
    egipcio = _legada(cpf=None, passaporte='A22215356', documento_identificador=None)
    americano = _legada(cpf=None, passaporte='B12345678', documento_identificador=None)
    AlunoFactory(
        pessoa_fisica=egipcio,
        nacionalidade='Estrangeira',
        pais_origem=PaisEdu.objects.create(sigla='EGY', nome='República Árabe Do Egito', codigo='178'),
    )
    AlunoFactory(
        pessoa_fisica=americano,
        nacionalidade='Estrangeira',
        pais_origem=PaisEdu.objects.create(sigla='USA', nome='Estados Unidos Da América (Eua)', codigo='249'),
    )

    _deduplicar()

    assert PessoaFisica.objects.get(pk=egipcio.pk).documento_identificador == 'EGY-A22215356'
    assert PessoaFisica.objects.get(pk=americano.pk).pais_origem == eua
    assert (PessoaFisica.objects.get(pk=egipcio.pk).pais_origem, planejar()) == (egito, {})


def test_mesmo_passaporte_sem_pais_nao_agrupa_e_vira_sempais() -> None:
    a = _legada(cpf=None, passaporte='AB123456', pais_origem=None, documento_identificador=None)
    b = _legada(cpf=None, passaporte='AB123456', pais_origem=None, documento_identificador=None)

    planejar()

    assert not D.objects.filter(pf_id__in=[a.pk, b.pk], acao__in=[D.MESCLADA, D.SEPARADA]).exists()
    sinteticos = set(D.objects.filter(pf_id__in=[a.pk, b.pk], acao=D.SINTETICO).values_list('documento', flat=True))
    assert sinteticos == {f'SEMPAIS-{a.pk}-AB123456', f'SEMPAIS-{b.pk}-AB123456'}


def _deduplicar() -> dict[str, int]:
    planejar()
    return aplicar()


def test_pf_sem_relacionamento_e_apagada_com_os_dependentes(pf_sem_relacionamento: None) -> None:
    orfa = _legada(cpf='abc')  # a higiene dela (CPF inválido) sai do plano
    PessoaEndereco.objects.create(pessoa=orfa, logradouro='Rua A')
    contato = ContatoEmergencia.objects.create(pessoa_fisica=orfa, nome_contato='Mãe', telefone='84999999999')
    com_comentario, com_prestador = PessoaFisicaFactory(), PessoaFisicaFactory()
    Comentario.objects.create(content_object=com_comentario, texto='Observação')
    PrestadorServicoFactory(pessoa_fisica=com_prestador)

    planejar()
    assert _acoes(orfa.pk) == {D.APAGADA}
    resumo = aplicar()

    assert resumo['apagadas'] == 1
    assert not PessoaFisica.objects.filter(pk=orfa.pk).exists()
    assert not PessoaEndereco.objects.filter(pessoa_id=orfa.pk).exists()
    assert not ContatoEmergencia.objects.filter(pk=contato.pk).exists()
    assert set(PessoaFisica.objects.values_list('pk', flat=True)) >= {com_comentario.pk, com_prestador.pk}
    assert D.objects.get(pf_id=orfa.pk).aplicado_em is not None


def test_pf_cujo_dependente_e_referenciado_nao_e_apagada(pf_sem_relacionamento: None) -> None:
    pessoa = PessoaFisicaFactory()
    externa = PessoaExterna.objects.bulk_create([PessoaExterna(pessoa_fisica=pessoa, cpf=CPF, nome='Ana')])[0]  # legada: sem vínculo
    externa.setores_adicionais.add(SetorFactory())

    planejar()

    assert D.APAGADA not in _acoes(pessoa.pk)


def _so_com_externa() -> tuple[PessoaFisica, PessoaExterna, Vinculo]:
    pessoa = PessoaFisicaFactory()
    externa = PessoaExterna(pessoa_fisica=pessoa, cpf=pessoa.cpf, nome='Ana')
    externa.save()  # cria o vínculo da externa, sem usuário
    return pessoa, externa, Vinculo.objects.get(pessoa=pessoa)


def test_pf_so_com_a_pessoa_externa_e_o_vinculo_dela_e_apagada(pf_sem_relacionamento: None) -> None:
    pessoa, externa, vinculo = _so_com_externa()

    resumo = _deduplicar()

    assert resumo['apagadas'] == 1
    assert not PessoaFisica.objects.filter(pk=pessoa.pk).exists()
    assert not PessoaExterna.objects.filter(pk=externa.pk).exists()
    assert not Vinculo.objects.filter(pk=vinculo.pk).exists()


def test_vinculo_da_externa_com_usuario_ou_referenciado_mantem_a_pf(pf_sem_relacionamento: None) -> None:
    com_usuario, _, vinculo = _so_com_externa()
    Vinculo.objects.filter(pk=vinculo.pk).update(user=UserFactory())
    referenciada, _, vinculo_referenciado = _so_com_externa()
    Comentario.objects.create(content_object=vinculo_referenciado, texto='Observação')

    planejar()

    assert D.APAGADA not in _acoes(com_usuario.pk) | _acoes(referenciada.pk)


def test_grupo_com_alguem_relacionado_mescla_e_grupo_todo_sem_relacionamento_e_apagado(pf_sem_relacionamento: None) -> None:
    orfa, relacionada = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    Comentario.objects.create(content_object=relacionada, texto='Observação')
    outro_cpf = '111.444.777-35'
    sem_ninguem = [PessoaFisicaFactory(cpf=outro_cpf), PessoaFisicaFactory(cpf=outro_cpf)]

    _deduplicar()

    assert not PessoaFisica.objects.filter(pk__in=[orfa.pk, *(p.pk for p in sem_ninguem)]).exists()
    assert D.objects.filter(pf_id=orfa.pk, acao=D.MESCLADA).exists()
    assert set(D.objects.filter(pf_id__in=[p.pk for p in sem_ninguem]).values_list('acao', flat=True)) == {D.APAGADA}
    assert PessoaFisica.objects.get(cpf=CPF).pk == relacionada.pk


def test_pf_que_ganha_relacionamento_depois_do_planejar_nao_e_apagada(pf_sem_relacionamento: None) -> None:
    pessoa = PessoaFisicaFactory()
    planejar()
    Comentario.objects.create(content_object=pessoa, texto='Observação')

    resumo = aplicar()

    linha = D.objects.get(pf_id=pessoa.pk, acao=D.APAGADA)
    assert resumo['apagadas'] == 0
    assert PessoaFisica.objects.filter(pk=pessoa.pk).exists()
    assert linha.aplicado_em is not None
    assert 'não apagada' in linha.motivo


def test_mescla_reaponta_fk_de_pf_e_de_pessoa_e_preserva_secret() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    contato = ContatoEmergencia.objects.create(pessoa_fisica=perdedora, nome_contato='Mãe', telefone='84999999999')
    endereco = PessoaEndereco.objects.create(pessoa=perdedora, logradouro='Rua A')
    externa = PessoaExterna(pessoa_fisica=perdedora, cpf=CPF, nome='Ana')
    externa.save()
    vinculo = Vinculo.objects.get(id_relacionamento=externa.pk, tipo_relacionamento__model='pessoaexterna')
    assert (vinculo.pessoa_id, PessoaFisica.objects.filter(cpf=CPF).count()) == (perdedora.pk, 2)

    _deduplicar()

    assert not PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    contato.refresh_from_db()
    endereco.refresh_from_db()
    vinculo.refresh_from_db()
    assert contato.pessoa_fisica_id == sobrevivente.pk
    assert endereco.pessoa_id == sobrevivente.pk
    assert vinculo.pessoa_id == sobrevivente.pk
    assert vinculo.secret == perdedora.pk
    assert D.objects.get(pf_id=perdedora.pk, acao=D.MESCLADA).aplicado_em is not None


def test_vinculo_reapontado_tem_a_busca_da_sobrevivente() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF, nome='Ana Perdedora'), PessoaFisicaFactory(cpf=CPF, nome='Ana Sobrevivente')
    externa = PessoaExterna(pessoa_fisica=perdedora, cpf=CPF, nome='Ana Perdedora')
    externa.save()
    vinculo = Vinculo.objects.get(pessoa=perdedora)
    assert 'ANA PERDEDORA' in vinculo.search

    _deduplicar()

    vinculo.refresh_from_db()
    assert vinculo.pessoa_id == sobrevivente.pk
    assert 'ANA SOBREVIVENTE' in vinculo.search
    assert 'ANA PERDEDORA' not in vinculo.search


def test_vinculo_da_separada_nao_e_mais_achado_pelo_cpf() -> None:
    separada = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    PessoaExterna(pessoa_fisica=separada, cpf=CPF, nome='Ana').save()
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1985, 5, 5))  # maior id: fica com o CPF no empate
    vinculo = Vinculo.objects.get(pessoa=separada)
    assert '529.982.247-25' in vinculo.search

    _deduplicar()

    vinculo.refresh_from_db()
    assert PessoaFisica.objects.get(pk=separada.pk).cpf is None
    assert '529.982.247-25' not in vinculo.search


def test_separada_fica_com_documento_conflito() -> None:
    separada = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 1, 1))

    _deduplicar()

    separada.refresh_from_db()
    assert separada.cpf is None
    assert separada.documento_identificador == f'CONFLITO-{separada.pk}-{CPF}'


def test_higiene_grava_sinteticos() -> None:
    sem = _legada(cpf='___.___.___-__', documento_identificador=None)
    invalido = _legada(cpf='529.982.247-24')

    _deduplicar()

    sem.refresh_from_db()
    invalido.refresh_from_db()
    assert (sem.cpf, sem.documento_identificador) == (None, f'SEMDOC-{sem.pk}')
    assert (invalido.cpf, invalido.documento_identificador) == (None, f'INVALIDO-{invalido.pk}-52998224724')


def test_passaporte_vira_documento_so_com_pais() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    com_pais = _legada(cpf=None, passaporte='AB123456', pais_origem=argentina, documento_identificador='AB123456')
    sem_pais = _legada(cpf=None, passaporte='CD654321', documento_identificador='CD654321')

    _deduplicar()

    com_pais.refresh_from_db()
    sem_pais.refresh_from_db()
    assert com_pais.documento_identificador == 'ARG-AB123456'
    # sem país não forma chave, mas o passaporte fica no sintético para ser achado
    assert (sem_pais.passaporte, sem_pais.documento_identificador) == ('CD654321', f'SEMPAIS-{sem_pais.pk}-CD654321')


def test_semdoc_gravado_vira_sempais_e_segue_o_passaporte() -> None:
    """SEMDOC-/SEMPAIS- seguem o passaporte atual (no aplicar e no save); CONFLITO-/INVALIDO- guardam a história e ficam."""
    sem_pais = _legada(cpf=None, passaporte='AAE771571', documento_identificador=None)
    historico = _legada(cpf=None, passaporte='CD654321', documento_identificador=None)
    PessoaFisica.objects.filter(pk=sem_pais.pk).update(documento_identificador=f'SEMDOC-{sem_pais.pk}')
    PessoaFisica.objects.filter(pk=historico.pk).update(documento_identificador=f'INVALIDO-{historico.pk}-52998224724')

    _deduplicar()

    sem_pais.refresh_from_db()
    assert sem_pais.documento_identificador == f'SEMPAIS-{sem_pais.pk}-AAE771571'
    assert PessoaFisica.objects.get(pk=historico.pk).documento_identificador == f'INVALIDO-{historico.pk}-52998224724'
    sem_pais.passaporte = 'XY998877'
    sem_pais.save()
    assert PessoaFisica.objects.get(pk=sem_pais.pk).documento_identificador == f'SEMPAIS-{sem_pais.pk}-XY998877'


def test_passaporte_do_aluno_sobrescreve_o_invalido() -> None:
    brasil = Pais.objects.create(codigo='024', nome='BRASIL', iso_alfa3='BRA')
    pessoa = _legada(cpf=None, passaporte='X', pais_origem=brasil, documento_identificador=None)
    AlunoFactory(pessoa_fisica=pessoa, passaporte='AB123456')

    _deduplicar()

    pessoa.refresh_from_db()
    assert (pessoa.passaporte, pessoa.documento_identificador) == ('AB123456', 'BRA-AB123456')


def test_vazio_do_sobrevivente_e_preenchido_e_divergencia_auditada() -> None:
    perdedora = PessoaFisicaFactory(cpf=CPF, rg='111', nome_mae='Joana')
    sobrevivente = PessoaFisicaFactory(cpf=CPF, rg=None, nome_mae='Maria')

    _deduplicar()

    sobrevivente.refresh_from_db()
    assert (sobrevivente.rg, sobrevivente.nome_mae) == ('111', 'Maria')
    assert D.objects.get(pf_id=perdedora.pk, acao=D.CAMPO_DESCARTADO, campo='nome_mae').valor_original == 'Joana'


def test_biometria_da_perdedora_preenche_o_sobrevivente_sem_biometria() -> None:
    PessoaFisicaFactory(cpf=CPF, template=b'\x01\x02')
    sobrevivente = PessoaFisicaFactory(cpf=CPF, template=None)

    _deduplicar()

    sobrevivente.refresh_from_db()
    assert bytes(sobrevivente.template) == b'\x01\x02'


def test_par_unico_repetido_fica_uma_vez() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_par_telefone ON comum_pessoatelefone (pessoa_id, numero)')
    for pessoa in (perdedora, sobrevivente):
        PessoaTelefone.objects.create(pessoa=pessoa, numero='84999999999')

    _deduplicar()

    assert PessoaTelefone.objects.filter(pessoa=sobrevivente, numero='84999999999').count() == 1


def test_null_na_unicidade_composta_nao_colide() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_par_endereco ON comum_pessoaendereco (pessoa_id, numero)')
    for pessoa, logradouro in ((perdedora, 'Rua A'), (sobrevivente, 'Rua B')):  # diferentes: o idêntico a limpeza apagaria
        PessoaEndereco.objects.create(pessoa=pessoa, logradouro=logradouro, numero=None)

    _deduplicar()

    assert PessoaEndereco.objects.filter(pessoa=sobrevivente).count() == 2


def test_colisao_em_indice_parcial_marca_erro_sem_apagar() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    with connection.cursor() as cursor:
        cursor.execute("CREATE UNIQUE INDEX tmp_parcial_telefone ON comum_pessoatelefone (pessoa_id, numero) WHERE ramal = ''")
    for pessoa in (perdedora, sobrevivente):
        PessoaTelefone.objects.create(pessoa=pessoa, numero='84999999999')

    resumo = _deduplicar()

    assert (resumo['mescladas'], resumo['erros']) == (0, 1)
    assert D.objects.filter(acao=D.ERRO, pf_id=sobrevivente.pk).exists()
    assert PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    assert PessoaTelefone.objects.filter(pessoa_id__in=[perdedora.pk, sobrevivente.pk]).count() == 2
    assert D.objects.get(pf_id=perdedora.pk, acao=D.MESCLADA).aplicado_em is None


def test_fk_set_null_ja_reapontada_nao_bloqueia_a_mescla(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outra instituição pode ter FK para pessoa com SET_NULL: o Collector a registra mesmo sem linhas."""
    monkeypatch.setattr(ContatoEmergencia._meta.get_field('pessoa_fisica').remote_field, 'on_delete', SET_NULL)
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    contato = ContatoEmergencia.objects.create(pessoa_fisica=perdedora, nome_contato='Mãe', telefone='84999999999')

    resumo = _deduplicar()

    contato.refresh_from_db()
    assert (resumo['mescladas'], resumo['erros']) == (1, 0)
    assert contato.pessoa_fisica_id == sobrevivente.pk


def test_cascade_por_referencia_nao_descoberta_marca_erro_sem_apagar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem a trava do Collector, o CASCADE do ORM apagaria a linha filha antes da PF, e nenhuma FK do banco reclamaria."""
    from rh.deduplicacao import aplicacao

    descobertas = [ref for ref in aplicacao.referencias() if ref.tabela != ContatoEmergencia._meta.db_table]
    monkeypatch.setattr(aplicacao, 'referencias', lambda: descobertas)
    perdedora, _ = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    contato = ContatoEmergencia.objects.create(pessoa_fisica=perdedora, nome_contato='Mãe', telefone='84999999999')

    resumo = _deduplicar()

    contato.refresh_from_db()
    assert (resumo['mescladas'], resumo['erros']) == (0, 1)
    assert PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    assert contato.pessoa_fisica_id == perdedora.pk
    assert 'comum.ContatoEmergencia' in D.objects.get(acao=D.ERRO).motivo


def test_gfk_para_a_perdedora_e_reapontada() -> None:
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    comentario = Comentario.objects.create(content_object=perdedora, texto='Observação')

    _deduplicar()

    comentario.refresh_from_db()
    assert comentario.object_id == sobrevivente.pk


def _api_externa() -> APIExterna:
    return APIExterna.objects.create(
        nome='API de teste', url_base='https://api.exemplo.br', tipo_autenticacao=APIExterna.TOKEN_AUTH, client_id='id', secret='segredo'
    )


def test_info_complementar_mantem_a_consulta_mais_recente() -> None:
    api = _api_externa()
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    antiga = PessoaInfoComplementar.objects.create(pessoa=sobrevivente, api_origem=api, informacoes={'v': 'antiga'})
    nova = PessoaInfoComplementar.objects.create(pessoa=perdedora, api_origem=api, informacoes={'v': 'nova'})

    _deduplicar()

    assert list(PessoaInfoComplementar.objects.filter(pessoa=sobrevivente).values_list('pk', flat=True)) == [nova.pk]
    assert not PessoaInfoComplementar.objects.filter(pk=antiga.pk).exists()


INFO_COMPLEMENTAR_REPETIDA = """SELECT count(*) FROM (
    SELECT pessoa_id, api_origem_id FROM rh_pessoainfocomplementar GROUP BY 1, 2 HAVING count(*) > 1
) g"""  # a consulta da trava da rh/0111 (MR 3)


def test_info_complementar_repetida_de_pessoa_fora_do_plano_fica_so_a_mais_recente() -> None:
    api = _api_externa()
    recentes = {}
    for pessoa in (PessoaFisicaFactory(), PessoaJuridicaFactory()):  # PF sem duplicata e PJ: nenhuma entra no dedup_mapa
        # a recente tem o pk menor: o desempate por pk sozinho não passaria
        recentes[pessoa.pk] = PessoaInfoComplementar.objects.create(pessoa=pessoa, api_origem=api, informacoes={'v': 'recente'}).pk
        antiga = PessoaInfoComplementar.objects.create(pessoa=pessoa, api_origem=api, informacoes={'v': 'antiga'})
        PessoaInfoComplementar.objects.filter(pk=antiga.pk).update(data_hora_consulta=antiga.data_hora_consulta - timedelta(days=30))

    _deduplicar()

    for pessoa_id, recente in recentes.items():
        assert list(PessoaInfoComplementar.objects.filter(pessoa_id=pessoa_id).values_list('pk', flat=True)) == [recente]
    with connection.cursor() as cursor:
        cursor.execute(INFO_COMPLEMENTAR_REPETIDA)
        assert cursor.fetchone() == (0,)


def test_referencia_fora_do_plano_marca_erro_sem_apagar() -> None:
    perdedora, _ = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    planejar()
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE tmp_ref (id serial PRIMARY KEY, pf integer REFERENCES pessoa_fisica (pessoa_ptr_id))')
        cursor.execute('INSERT INTO tmp_ref (pf) VALUES (%s)', [perdedora.pk])

    resumo = aplicar()

    assert resumo['erros'] == 1
    assert PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    assert D.objects.filter(acao=D.ERRO).exists()


def test_replanejar_depois_de_aplicar_preserva_o_conflito() -> None:
    separada = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1991, 1, 1))
    _deduplicar()

    _deduplicar()  # o runbook manda replanejar para recuperar de `erro`

    separada.refresh_from_db()
    assert separada.documento_identificador == f'CONFLITO-{separada.pk}-{CPF}'


def test_aplicar_de_novo_nao_faz_nada() -> None:
    PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    _deduplicar()

    assert aplicar()['mescladas'] == 0


def test_pf_do_plano_que_sumiu_vira_erro_so_do_seu_grupo() -> None:
    outro_cpf = '390.533.447-05'
    sumida, sobrevivente_do_plano_velho = PessoaFisicaFactory(cpf=CPF), PessoaFisicaFactory(cpf=CPF)
    perdedora, sobrevivente = PessoaFisicaFactory(cpf=outro_cpf), PessoaFisicaFactory(cpf=outro_cpf)
    planejar()
    sumida_pk = sumida.pk
    sumida.delete()

    resumo = aplicar()

    assert (resumo['mescladas'], resumo['erros']) == (1, 1)
    erro = D.objects.get(acao=D.ERRO)
    assert erro.pf_id == sobrevivente_do_plano_velho.pk
    assert erro.motivo == f'PF do plano não existe mais: {sumida_pk}; rode planejar de novo'
    assert not PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    assert PessoaFisica.objects.filter(pk=sobrevivente.pk).exists()


def test_mescla_de_pessoa_ja_corrigida_vira_erro_do_grupo() -> None:
    corrigido = '390.533.447-05'
    a = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    b = _legada(cpf=CPF, documento_identificador=CPF, nascimento_data=None)  # com o CPF de A por erro; maior id, vence
    planejar()
    assert D.objects.get(pf_id=a.pk, acao=D.MESCLADA).sobrevivente_id == b.pk
    b.cpf = corrigido  # a secretaria corrige o CPF de B entre o planejar e o aplicar
    b.save()

    resumo = aplicar()

    assert (resumo['mescladas'], resumo['erros']) == (0, 1)
    assert 'rode planejar de novo' in D.objects.get(acao=D.ERRO, sobrevivente_id=b.pk).motivo
    assert PessoaFisica.objects.get(pk=a.pk).cpf == CPF
    assert PessoaFisica.objects.get(pk=b.pk).cpf == corrigido


def test_higiene_nao_anula_cpf_corrigido_depois_do_planejar() -> None:
    pessoa = _legada(cpf='123.456.789-00', documento_identificador='123.456.789-00')
    planejar()
    assert D.CPF_ANULADO in _acoes(pessoa.pk)
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf=CPF)  # alguém grava o CPF válido antes do aplicar

    aplicar()

    pessoa.refresh_from_db()
    assert (pessoa.cpf, pessoa.documento_identificador) == (CPF, CPF)
    erro = D.objects.get(pf_id=pessoa.pk, acao=D.ERRO, campo='cpf')
    assert (erro.aplicado_em, erro.valor_original) == (None, '123.456.789-00')
    assert erro.motivo == 'plano desatualizado (cpf_anulado); rode planejar de novo'  # a ação original legível na linha ERRO


def _pf_com_servidor_aluno_e_prestador(ocupacao_ativa: bool) -> PessoaFisica:
    """PF com servidor e aluno inativos e um prestador; com ocupação vigente, o prestador fica ativo e a PF vence o grupo."""
    pessoa = PessoaFisicaFactory(cpf=CPF, nome_registro='Maria da Silva Souza')
    ServidorFactory(pessoa_fisica=pessoa, ativo=False)
    jubilado = SituacaoMatriculaFactory(id=SituacaoMatricula.JUBILADO, descricao='Jubilado', ativo=False)
    AlunoFactory(pessoa_fisica=pessoa, situacao=jubilado)
    prestador = PrestadorServicoFactory(pessoa_fisica=pessoa, matricula='52998224725', ativo=False)
    if ocupacao_ativa:
        OcupacaoPrestador.objects.create(
            prestador=prestador,
            ocupacao=Ocupacao.objects.create(descricao='Vigilante'),
            empresa=PessoaJuridicaFactory(),
            data_inicio=date.today() - timedelta(days=30),
            data_fim=date.today() + timedelta(days=30),
        )
    return pessoa


def _flags(pessoa: PessoaFisica) -> tuple[bool, bool, bool, bool]:
    pessoa.refresh_from_db()
    return pessoa.eh_servidor, pessoa.eh_aluno, pessoa.eh_prestador, pessoa.eh_usuarioexterno


def test_mescla_recalcula_vinculos_nomes_e_busca_do_sobrevivente(sync_permissions: None) -> None:
    perdedora = _pf_com_servidor_aluno_e_prestador(ocupacao_ativa=False)  # tudo inativo: perde para a mais nova
    sobrevivente = _legada(cpf=CPF, nome='', nome_registro='', nome_social='', nome_usual='')
    assert _flags(sobrevivente) == (False, False, False, False)

    _deduplicar()

    assert not PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    assert _flags(sobrevivente) == (True, True, True, True)  # prestador sem ocupação vigente é usuário externo
    assert (sobrevivente.nome_registro, sobrevivente.nome, sobrevivente.nome_usual) == ('Maria da Silva Souza',) * 2 + ('Maria Souza',)
    usernames = [u for u in Vinculo.objects.filter(pessoa_id=sobrevivente.pk).values_list('user__username', flat=True) if u]
    assert usernames  # os vínculos da perdedora vieram com usuário e agora são do sobrevivente
    assert sobrevivente.search_fields_optimized.startswith(f'Maria da Silva Souza{CPF}52998224725')
    assert all(username in sobrevivente.search_fields_optimized for username in usernames)


def test_mescla_recalcula_vinculos_desatualizados_do_sobrevivente(sync_permissions: None) -> None:
    sobrevivente = _pf_com_servidor_aluno_e_prestador(ocupacao_ativa=True)
    perdedora = _legada(cpf=CPF)
    # flags gravadas erradas no legado: a mescla as recalcula pelos vínculos
    PessoaFisica.objects.filter(pk__in=[sobrevivente.pk, perdedora.pk]).update(
        eh_servidor=False, eh_aluno=False, eh_prestador=False, eh_usuarioexterno=True
    )

    _deduplicar()

    assert not PessoaFisica.objects.filter(pk=perdedora.pk).exists()
    assert _flags(sobrevivente) == (True, True, True, False)  # ocupação vigente: não é usuário externo


def _queries_do_preenchimento(sobreviventes: int) -> int:
    grupos = {}
    for _ in range(sobreviventes):
        perdedora = PessoaFisicaFactory(rg='111')
        grupos[PessoaFisicaFactory(cpf=perdedora.cpf).pk] = [perdedora.pk]
    with CaptureQueriesContext(connection) as queries:
        _preencher_sobreviventes(grupos)
    assert set(PessoaFisica.objects.filter(pk__in=list(grupos)).values_list('rg', flat=True)) == {'111'}
    return len(queries)


def test_preenchimento_dos_sobreviventes_nao_cresce_com_o_lote() -> None:
    assert _queries_do_preenchimento(6) == _queries_do_preenchimento(2)


def _queries_do_delete(perdedoras: int) -> list[str]:
    pks = [PessoaFisicaFactory().pk for _ in range(perdedoras)]
    with CaptureQueriesContext(connection) as queries:
        _apagar_perdedoras(pks)
    assert not PessoaFisica.objects.filter(pk__in=pks).exists()
    return [query['sql'] for query in queries.captured_queries]


def test_delete_das_perdedoras_coleta_uma_vez_e_nao_cresce_com_o_lote() -> None:
    seis, dois = _queries_do_delete(6), _queries_do_delete(2)

    assert len(seis) == len(dois)
    assert len(set(dois)) == len(dois)  # a coleta da trava é a do DELETE: nenhuma consulta se repete


def _queries_da_higiene(sem_documento: int) -> int:
    pks = [_legada(cpf=None, documento_identificador=None).pk for _ in range(sem_documento)]
    planejar()
    with CaptureQueriesContext(connection) as queries:
        _aplicar_higiene()
    assert D.objects.filter(pf_id__in=pks, acao=D.SINTETICO, aplicado_em__isnull=False).count() == sem_documento
    assert set(PessoaFisica.objects.filter(pk__in=pks).values_list('documento_identificador', flat=True)) == {f'SEMDOC-{pk}' for pk in pks}
    return len(queries)


def test_higiene_nao_cresce_com_o_numero_de_linhas() -> None:
    _queries_da_higiene(1)  # aplica antes a higiene de PFs que outro teste tenha deixado no banco: as duas medidas veem só as suas
    assert _queries_da_higiene(6) == _queries_da_higiene(2)


def test_duas_linhas_da_mesma_pf_numa_acao_valem_em_ordem() -> None:
    # o planejar não gera isso; se houver, a 2ª linha vê a PF como a 1ª a deixou, como no linha a linha
    pessoa = _legada(cpf='123.456.789-00', documento_identificador='123.456.789-00')
    primeira = D.objects.create(pf_id=pessoa.pk, acao=D.CPF_ANULADO, campo='cpf', valor_original='123.456.789-00')
    segunda = D.objects.create(pf_id=pessoa.pk, acao=D.CPF_ANULADO, campo='cpf', valor_original='123.456.789-00')

    assert _aplicar_higiene() == 1

    pessoa.refresh_from_db()
    assert pessoa.cpf is None
    assert D.objects.get(pk=primeira.pk).aplicado_em is not None
    assert D.objects.get(pk=segunda.pk).acao == D.ERRO


def test_cpf_anulado_grava_o_sintetico_junto() -> None:
    # na Release 2 a CHECK "sem CPF exige país" não é deferível: o CPF anulado não pode ficar sem documento nem por um instante
    pessoa = _legada(cpf='123.456.789-00', documento_identificador='123.456.789-00')
    D.objects.create(pf_id=pessoa.pk, acao=D.CPF_ANULADO, campo='cpf', valor_original='123.456.789-00')

    assert _aplicar_higiene() == 1

    pessoa.refresh_from_db()
    assert (pessoa.cpf, pessoa.documento_identificador) == (None, f'INVALIDO-{pessoa.pk}-12345678900')


def test_normalizacao_da_sintetico_a_pf_sem_chave_como_o_save() -> None:
    pessoa = _legada(cpf=None, passaporte=None, documento_identificador='LIXO')

    _aplicar_higiene()  # sem linha no plano: só a normalização

    pessoa.refresh_from_db()
    assert pessoa.documento_identificador == f'SEMDOC-{pessoa.pk}'
