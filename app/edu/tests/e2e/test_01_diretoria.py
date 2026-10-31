"""Fluxo 001: configurar a diretoria acadêmica.

Primeiro elo da cadeia do edu — sem diretoria não há curso, turma nem matrícula. É
também a tela que exercita o padrão de popup em iframe (fancybox) que se repete em quase
todo o módulo, e a atribuição de grupo COM ESCOPO DE SETOR, que é como o edu resolve
permissão (``UsuarioGrupoSetor``), diferente do grupo global do resto do SUAP.
"""

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import abrir_popup, escolher_autocomplete, mensagem_de_sucesso
from djtools.e2e_ui import esperar_desfecho_do_popup, marcar_documento

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/edu/diretoria/'
FORM = '/admin/edu/diretoria/add/'


def test_cadastra_diretoria_academica(logado_edu, setor_livre):
    """Associa um setor existente a uma diretoria acadêmica nova.

    Não usa ``DIAC/CEN``: o replay ORM já tornou aquele setor uma diretoria, e
    ``Diretoria.setor`` é único.
    """
    from edu.models import Diretoria

    sigla = setor_livre()
    page = logado_edu('admin_academico')
    page.goto(FORM)
    escolher_autocomplete(page, 'setor', sigla)
    page.fill('input[name=titulo_autoridade_maxima_masculino]', 'Reitor')
    page.fill('input[name=titulo_autoridade_maxima_feminino]', 'Reitora')
    page.click('input[name=_save]')

    mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
    assert Diretoria.objects.filter(setor__sigla=sigla).exists(), 'a UI disse que salvou, mas não persistiu'


def test_cadastra_diretoria_sistemica(logado_edu, setor_livre):
    """Diretoria do tipo Sistêmica: é ela que habilita os perfis com acesso a todos os campi.

    O replay já criou a sistêmica sobre a RAIZ (é dela que o Operador ENADE e o Diretor de
    Avaliação e Regulação do Ensino dependem, ver ``test_14_enade``), então aqui o cadastro
    acontece sobre outro setor — o que se cobre é o caminho do formulário, inclusive o campo
    ``Tipo``, que é o que diferencia sistêmica de acadêmica.
    """
    from edu.models import Diretoria

    sigla = setor_livre()
    page = logado_edu('admin_academico')
    page.goto(FORM)
    escolher_autocomplete(page, 'setor', sigla)
    page.select_option('select[name=tipo]', label='Sistêmica')
    page.click('input[name=_save]')

    mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
    diretoria = Diretoria.objects.get(setor__sigla=sigla)
    assert diretoria.is_diretoria_sistemica(), 'diretoria criada, mas não como sistêmica'


def test_listagem_mostra_a_diretoria_do_campus(logado_edu):
    page = logado_edu('admin_academico')
    page.goto(LISTAGEM)
    expect(page.get_by_role('heading', name='Diretorias Acadêmicas')).to_be_visible()
    expect(page.get_by_text('DIAC/CEN').first).to_be_visible()


@pytest.mark.parametrize(
    ('aba', 'grupo'),
    [
        ('Direção', 'Diretor Geral'),
        ('Direção', 'Diretor Acadêmico'),
        ('Secretaria Acadêmica', 'Secretário Acadêmico'),
    ],
)
def test_vincula_papel_da_diretoria(logado_edu, grupo_temporario, aba, grupo):
    """Cada aba da diretoria atribui um papel do edu com escopo no setor dela.

    Um caso por papel porque cada um é um grupo diferente e o que se está verificando é
    exatamente o par (aba, grupo): trocar o grupo de aba é a regressão típica desta tela.
    Todos usam o professor 100007 como alvo — o replay não lhe deu nenhum grupo com escopo,
    então o vínculo criado aqui é observável, e o ``grupo_temporario`` o desfaz.
    """
    from edu.models import Diretoria
    from djtools.e2e_ui import Tela

    diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
    vinculos = grupo_temporario(grupo)
    assert not vinculos.exists(), 'o professor já estava neste grupo: o teste não mediria nada'

    tela = Tela(logado_edu('admin_academico')).ir(f'/edu/diretoria/{diretoria.pk}/')
    tela.clicar_aba(aba)
    tela.clicar_botao(f'Adicionar {grupo}')
    popup = tela.popup()
    popup.preencher('Usuário', 'autocomplete', '100007')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Usuário adicionado com sucesso.')
    assert vinculos.filter(setor=diretoria.setor).exists(), f'vínculo de {grupo} não gravado no setor da diretoria'


@pytest.mark.parametrize('grupo', ['Diretor de Avaliação e Regulação do Ensino', 'Operador ENADE'])
def test_vincula_papel_sistemico(logado_edu, grupo_temporario, grupo):
    """Os papéis sistêmicos só existem na diretoria Sistêmica — e são a porta do ENADE.

    ``edu/views/diretorias.py`` monta as dimensões de forma diferente quando
    ``is_diretoria_sistemica()``: o Diretor de Avaliação e Regulação do Ensino aparece em
    "Direção" e o Operador ENADE em "Outras Atividades". Sem estes dois vínculos a
    funcionalidade 013 não tem quem a execute.
    """
    from edu.models import Diretoria
    from djtools.e2e_ui import Tela

    sistemica = Diretoria.objects.get(setor__sigla='RAIZ', tipo=Diretoria.TIPO_SISTEMICA)
    vinculos = grupo_temporario(grupo)

    tela = Tela(logado_edu('admin_academico')).ir(f'/edu/diretoria/{sistemica.pk}/')
    tela.clicar_aba('Direção' if grupo.startswith('Diretor') else 'Outras Atividades')
    tela.clicar_botao(f'Adicionar {grupo}')
    popup = tela.popup()
    popup.preencher('Usuário', 'autocomplete', '100007')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Usuário adicionado com sucesso.')
    assert vinculos.filter(setor=sistemica.setor).exists(), f'vínculo sistêmico de {grupo} não gravado'


def test_vincula_coordenador_de_registros_academicos(logado_edu, grupo_temporario):
    """O responsável pela emissão do diploma tem cadastro próprio, com portaria.

    Não é só um vínculo de grupo: a tela cria um ``CoordenadorRegistroAcademico`` ligado à
    diretoria, e é esse registro que a emissão de diploma (funcionalidade 010) exige.
    """
    from edu.models import CoordenadorRegistroAcademico, Diretoria
    from djtools.e2e_ui import Tela

    diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
    grupo_temporario('Coordenador de Registros Acadêmicos')
    coordenadores = CoordenadorRegistroAcademico.objects.filter(diretoria=diretoria, servidor__matricula='100007')
    try:
        tela = Tela(logado_edu('admin_academico')).ir(f'/edu/diretoria/{diretoria.pk}/')
        tela.clicar_aba('Formatura/Diplomas')
        tela.clicar_botao('Adicionar Coordenador de Registros Acadêmicos')
        popup = tela.popup()
        popup.preencher('Servidor', 'autocomplete', '100007')
        popup.preencher('Número da Portaria', 'texto', '123/2019')
        popup.salvar_no_popup('Salvar')

        tela.sucesso('Responsável pela Emissão do Diploma cadastrado/atualizado com sucesso.')
        assert coordenadores.exists(), 'responsável pela emissão do diploma não persistido'
    finally:
        coordenadores.delete()


def test_vincula_coordenador_de_curso_pela_aba(logado_edu):
    """Adiciona um usuário ao grupo "Coordenador de Curso" no setor da diretoria.

    Vínculo por popup: o link ``.popup`` abre um iframe do fancybox e, ao salvar, a view
    responde com ``close_popup=True`` — a mensagem de sucesso aparece na página de trás.
    Usa o professor (100007), que o replay não colocou em nenhum grupo com escopo.
    """
    from django.contrib.auth.models import Group

    from comum.models import UsuarioGrupo, UsuarioGrupoSetor
    from edu.models import Diretoria

    diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
    grupo = Group.objects.get(name='Coordenador de Curso')
    vinculos = UsuarioGrupoSetor.objects.filter(usuario_grupo__group=grupo, usuario_grupo__user__username='100007', setor=diretoria.setor)
    page = logado_edu('admin_academico')
    try:
        page.goto(f'/edu/diretoria/{diretoria.pk}/?tab=coordenacao-academica')

        popup = abrir_popup(page, 'Adicionar Coordenador de Curso')
        escolher_autocomplete(page, 'vinculo', '100007', escopo=popup)
        marcar_documento(page)
        popup.locator('input[type=submit]').first.click()
        # Sem esperar o desfecho do popup, a asserção conta seus 15s ainda no documento
        # antigo, que nunca terá o banner (#16990).
        esperar_desfecho_do_popup(page)

        mensagem_de_sucesso(page, 'Usuário adicionado com sucesso.')
        assert vinculos.exists(), 'vínculo de grupo não gravado no setor da diretoria'
    finally:
        # Sem desfazer, o professor 100007 sairia daqui podendo gerar turmas e aprovar
        # plano de ensino — os módulos 03 e 05 medem justamente o contrário. O
        # `UsuarioGrupo` também tem de ir: é ele que espelha o vínculo em `user.groups`,
        # e só apagar o `UsuarioGrupoSetor` deixaria a permissão global de pé.
        vinculos.delete()
        UsuarioGrupo.objects.filter(group=grupo, user__username='100007').delete()


def test_professor_nao_cadastra_diretoria(logado_edu):
    """Cadastro de diretoria é do Administrador Acadêmico; um servidor comum não entra."""
    page = logado_edu('professor')
    assert page.goto(FORM).status == 403
