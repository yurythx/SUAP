"""Fluxo: a caixa de comentários genérica, que qualquer model do SUAP pendura em si.

``Comentario`` liga-se ao objeto comentado por ``GenericForeignKey``, e as três rotas do
``comum`` são as únicas que o gravam: comentar, responder um comentário e desconsiderar o
próprio. Quem as publica na tela é a templatetag ``comentarios`` do ``djtools``, usada por vários
apps — o formulário é do ``comum``, o objeto comentado é de quem chamar.

A regressão que este arquivo pega está no par (app, model, id) da URL: ele vem **da rota**, não
de um formulário, e é resolvido por ``ContentType.objects.get(app_label=..., model=...)`` já
dentro da view. Se essa resolução escorregar, o comentário é gravado — e some, porque fica preso
a outro objeto. Nada falha; o texto simplesmente não aparece onde foi escrito.

O objeto comentado é um ``Predio`` criado e apagado pelo próprio teste (fixture
``objeto_comentavel``): é model do próprio ``comum``, o que evita inverter a dependência entre
apps só para ter onde pendurar um comentário.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo, com `{}` no lugar do parâmetro — armadilha 17 da receita.
COMENTARIO_ADD = '/comum/comentario/add/{aplicacao}/{modelo}/{objeto}/'
COMENTARIO_RESPONDER = '/comum/comentario/add/{aplicacao}/{modelo}/{objeto}/{resposta}/'
COMENTARIO_DESCONSIDERAR = '/comum/comentario/desconsiderar/{comentario}/'


def test_ciclo_do_comentario(logado_efemero, usuario_do_inicio, objeto_comentavel):
    """Comenta um objeto, responde o próprio comentário e desconsidera a resposta.

    Uma cadeia e não três testes porque os dois últimos gestos só existem sobre o primeiro: a
    resposta precisa do ``resposta_id`` de um comentário, e ``desconsiderar`` exige que o
    usuário logado seja o autor (``request.user != comentario.cadastrado_por`` levanta
    ``PermissionDenied``). Forjados por ORM, os dois passariam a afirmar o próprio setup — e o
    autor, que é o ponto da regra, viria de um ``CurrentUserField`` sem request.

    O que se afirma em cada passo é o vínculo, não o texto: o ``content_type``/``object_id`` do
    primeiro (o par que a rota carrega), o ``resposta_id`` do segundo (a árvore que a
    templatetag desenha) e o ``desconsiderado`` do terceiro — que é o único "apagar" que o SUAP
    oferece aqui, porque o comentário não é removido, é riscado.

    O rótulo do botão é ``Enviar`` e não ``Salvar``: ``ComentarioForm`` é um ``FormPlus``, não
    um ``ModelForm``, e o ``render_form`` do djtools só põe ``Salvar`` nos segundos.
    """
    from django.contrib.contenttypes.models import ContentType

    from comum.models import Comentario, Predio

    autor = usuario_do_inicio.get_user()
    tipo = ContentType.objects.get_for_model(Predio)
    endereco = {'aplicacao': 'comum', 'modelo': 'predio', 'objeto': objeto_comentavel.pk}
    texto = 'Prédio com obra de acessibilidade prevista para o próximo semestre.'

    tela = Tela(logado_efemero('dono_do_inicio')).ir(COMENTARIO_ADD.format(**endereco))
    tela.preencher('Texto', 'textarea', texto)
    tela.clicar_botao('Enviar')

    tela.sucesso('Comentário adicionado com sucesso.')
    comentario = Comentario.objects.filter(content_type=tipo, object_id=objeto_comentavel.pk, texto=texto).first()
    assert comentario is not None, 'a UI disse que adicionou, mas o comentário não persistiu no objeto informado na rota'
    assert comentario.cadastrado_por == autor, 'o comentário foi gravado em nome de outro usuário'

    resposta_texto = 'A obra foi confirmada pela direção do campus.'
    tela.ir(COMENTARIO_RESPONDER.format(**endereco, resposta=comentario.pk))
    tela.preencher('Texto', 'textarea', resposta_texto)
    tela.clicar_botao('Enviar')

    tela.sucesso('Comentário adicionado com sucesso.')
    resposta = Comentario.objects.filter(content_type=tipo, object_id=objeto_comentavel.pk, texto=resposta_texto).first()
    assert resposta is not None, 'a UI disse que adicionou, mas a resposta não persistiu'
    assert resposta.resposta_id == comentario.pk, 'a resposta foi gravada solta, sem o comentário que ela responde'

    tela.ir(COMENTARIO_DESCONSIDERAR.format(comentario=resposta.pk))

    tela.sucesso('Comentário desconsiderado com sucesso.')
    resposta.refresh_from_db()
    assert resposta.desconsiderado, 'a UI disse que desconsiderou, mas o comentário continua valendo'


def test_nao_desconsidera_comentario_de_outra_pessoa(servidores_comum, logado_efemero, usuario_do_inicio, objeto_comentavel):
    """Só o autor risca o próprio comentário — e a recusa é 403, não uma tela sem botão.

    Vale um teste próprio porque a guarda é da **view**, não da templatetag: quem monta a caixa
    só desenha o botão para o autor (``context['user'] == item.cadastrado_por``), de modo que a
    proteção parece existir enquanto se olha a tela. É a view que a garante, e é ela que um
    ``GET`` direto na URL põe à prova.

    A mesma linha barra o segundo clique do próprio autor (``comentario.desconsiderado`` já
    ``True``), então esta é a asserção de duas regras num gesto só.
    """
    from django.contrib.contenttypes.models import ContentType

    from comum.models import Comentario, Predio

    alheio = Comentario.objects.create(
        # Explícito porque `cadastrado_por` é `CurrentUserField`: numa fixture/teste não há
        # request no threadlocal do djtools e o default cairia em `None`.
        cadastrado_por=servidores_comum['solicitante'].get_user(),
        content_type=ContentType.objects.get_for_model(Predio),
        object_id=objeto_comentavel.pk,
        texto='Comentário de outra pessoa (e2e).',
    )

    tela = Tela(logado_efemero('dono_do_inicio'))
    resposta = tela.buscar(COMENTARIO_DESCONSIDERAR.format(comentario=alheio.pk))

    assert resposta.status == 403, f'desconsiderar comentário alheio devolveu HTTP {resposta.status} em vez de 403'
    alheio.refresh_from_db()
    assert not alheio.desconsiderado, 'o SUAP respondeu 403 e mesmo assim riscou o comentário de outra pessoa'
