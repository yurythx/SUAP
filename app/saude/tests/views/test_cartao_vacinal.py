"""Testes do cartão vacinal: aprazamento, reforço e ordenação de exibição."""

from django.contrib.auth.models import Group

from rh.tests.factories import ServidorFactory
from saude.models import CartaoVacinal, Vacina


def test_registrar_previsao_permite_medico(suap_client, sync_permissions, prontuario):
    """Médico também deve poder registrar aprazamento, assim como enfermagem."""
    vacina = Vacina.objects.create(nome='Covid-19', doses=2)
    vacinacao = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, numero_dose=1)

    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Médico'))
    suap_client.login(user=user)

    response = suap_client.post(f'/saude/registrar_previsao/{vacinacao.id}/', {'previsao': '01/12/2026'})

    assert response.status_code == 302
    vacinacao.refresh_from_db()
    assert vacinacao.data_prevista.isoformat() == '2026-12-01'


def test_adicionar_reforco_cria_registro_de_reforco(profissional, prontuario):
    vacina = Vacina.objects.create(nome='Covid-19', doses=2)

    response = profissional.get(f'/saude/adicionar_reforco/{prontuario.id}/{vacina.id}/')

    assert response.status_code == 302
    reforco = CartaoVacinal.objects.get(prontuario=prontuario, vacina=vacina)
    assert reforco.eh_reforco is True
    assert reforco.numero_dose == 1
    assert reforco.get_numero_dose() == 'Reforço'


def test_adicionar_reforco_permite_multiplos_reforcos_para_mesma_vacina(profissional, prontuario):
    vacina = Vacina.objects.create(nome='Covid-19', doses=2)

    profissional.get(f'/saude/adicionar_reforco/{prontuario.id}/{vacina.id}/')
    profissional.get(f'/saude/adicionar_reforco/{prontuario.id}/{vacina.id}/')

    reforcos = CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina, eh_reforco=True).order_by('numero_dose')
    assert [r.numero_dose for r in reforcos] == [1, 2]
    assert [r.get_numero_dose() for r in reforcos] == ['Reforço', '2º Reforço']


def test_pode_vacinar_segundo_reforco_depende_da_aplicacao_do_primeiro(prontuario):
    vacina = Vacina.objects.create(nome='Covid-19', doses=2)
    primeiro_reforco = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=True, numero_dose=1)
    segundo_reforco = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=True, numero_dose=2)

    assert primeiro_reforco.pode_vacinar() is True
    assert segundo_reforco.pode_vacinar() is False

    primeiro_reforco.data_vacinacao = '2026-01-10'
    primeiro_reforco.save()

    assert segundo_reforco.pode_vacinar() is True


def test_pode_vacinar_nao_estoura_em_registro_legado_numero_dose_zero(prontuario):
    """Um numero_dose=0 remanescente (linha não migrada pela 0037, ou criada por outro caminho)
    cai na mesma guarda de numero_dose<=1, sem tentar buscar uma dose anterior inexistente."""
    vacina = Vacina.objects.create(nome='Covid-19', doses=2)
    registro_legado = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=False, numero_dose=0)

    assert registro_legado.pode_vacinar() is True


def test_pode_vacinar_nao_estoura_com_buraco_na_numeracao(prontuario):
    """Se a dose anterior na sequência não existir (buraco de numeração), pode_vacinar deve
    retornar False em vez de deixar .latest('id') estourar DoesNotExist."""
    vacina = Vacina.objects.create(nome='Covid-19', doses=3)
    terceira_dose = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=False, numero_dose=3)

    assert terceira_dose.pode_vacinar() is False


def test_adicionar_reforco_requer_grupo_saude(suap_client, sync_permissions, prontuario):
    vacina = Vacina.objects.create(nome='Covid-19', doses=2)
    # servidor sem nenhum grupo de saúde: é o que deve levar ao 403.
    suap_client.login(user=ServidorFactory().get_user())

    response = suap_client.get(f'/saude/adicionar_reforco/{prontuario.id}/{vacina.id}/')

    assert response.status_code == 403
    assert not CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina).exists()


def test_cartao_vacinal_exibe_dose_mais_recente_primeiro(profissional, prontuario):
    vacina = Vacina.objects.create(nome='Covid-19', doses=3)
    dose_1 = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, numero_dose=1, data_vacinacao='2026-02-14')
    dose_2 = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, numero_dose=2, data_vacinacao='2026-06-14')
    reforco = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=True, numero_dose=1, data_vacinacao='2026-09-14')

    response = profissional.get(f'/saude/prontuario/{prontuario.vinculo_id}/?tab=aba_cartao_vacinal')

    assert response.status_code == 200
    [grupo] = [g for g in response.context['grupos'] if g and g[0].vacina_id == vacina.id]
    assert [registro.id for registro in grupo] == [reforco.id, dose_2.id, dose_1.id]
