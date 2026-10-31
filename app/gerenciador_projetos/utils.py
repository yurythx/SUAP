from __future__ import annotations

from random import randint
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from django.conf import settings
from django.template.defaultfilters import linebreaksbr
from django.utils.html import escape

from comum.utils import tl
from djtools.utils import send_notification

if TYPE_CHECKING:
    from comum.models import User
    from gerenciador_projetos.models import Tarefa


def generate_color():
    color = '#{:02x}{:02x}{:02x}'.format(*(randint(0, 255) for x in range(3)))
    return color


def dados_gerais(tarefa: Tarefa) -> str:
    dados = [
        f'<dt>Tarefa:</dt><dd>{escape(tarefa.titulo)}</dd>',
        f'<dt>Situação:</dt><dd>{escape(tarefa.get_situacao_display())}</dd>',
    ]
    dados.append(f'<dt>Prioridade:</dt><dd>{escape(tarefa.get_prioridade_display())}</dd>')
    atribuidos = ', '.join(escape(usuario) for usuario in tarefa.atribuido_a.all())
    if atribuidos:
        dados.append(f'<dt>Atribuído a:</dt><dd>{atribuidos}</dd>')
    dados.append(f'<dt>Criada em:</dt><dd>{tarefa.aberto_em.strftime("%d/%m/%Y %H:%M")}</dd>')
    for rotulo, data in (
        ('Data de início', tarefa.data_inicio),
        ('Data estimada de conclusão', tarefa.data_conclusao_estimada),
        ('Data de conclusão', tarefa.data_conclusao),
    ):
        if data:
            dados.append(f'<dt>{rotulo}:</dt><dd>{data.strftime("%d/%m/%Y")}</dd>')
    url_tarefa = urljoin(f'{settings.SITE_URL.rstrip("/")}/', tarefa.get_absolute_url().lstrip('/'))
    return (
        f'<div class="dados-gerais"><h3>Dados da tarefa</h3><dl>{"".join(dados)}</dl></div>'
        f'<p class="more-info">Para mais informações, acesse: <a href="{url_tarefa}">{url_tarefa}</a></p>'
    )


class Notificar:
    @staticmethod
    def situacao_tarefa_alterada(tarefa: Tarefa, situacao_anterior: str, situacao_nova: str, autor: User | None) -> None:
        destinatarios = set(tarefa.atribuido_a.all()) | set(tarefa.observadores.all()) | set(tarefa.projeto.interessados.all())
        if autor:
            destinatarios.discard(autor)
        if not destinatarios:
            return
        mensagem = (
            '<h1>Gerenciador de Projetos: Situação de tarefa alterada</h1>'
            f'<h2>Projeto: {escape(tarefa.projeto.titulo)}</h2>'
            f'<p>Situação alterada de <strong class="text-danger">{escape(situacao_anterior)}</strong> para <strong class="text-success">{escape(situacao_nova)}</strong>.</p>'
            f'{dados_gerais(tarefa)}'
        )
        send_notification(
            assunto='[SUAP] Gerenciador de Projetos: Situação de tarefa alterada',
            mensagem=mensagem,
            de=settings.DEFAULT_FROM_EMAIL,
            vinculos=[usuario.get_vinculo() for usuario in destinatarios],
        )

    @staticmethod
    def nova_atividade_tarefa(tarefa: Tarefa, tipo: str, autor: User, descricao: str) -> None:
        destinatarios = set(tarefa.atribuido_a.all()) | set(tarefa.observadores.all()) | set(tarefa.projeto.interessados.all())
        destinatarios.discard(autor)
        if not destinatarios:
            return
        usuario = escape(autor.get_profile().nome_usual)
        if tipo == 'comentário':
            rotulo = f'Comentário por {usuario}:'
        elif tipo == 'anexo':
            rotulo = f'Arquivo anexado por {usuario}:'
        else:
            rotulo = f'Link adicionado por {usuario}:'
        conteudo = linebreaksbr(descricao) if tipo == 'comentário' else escape(descricao)
        mensagem = (
            f'<h1>Gerenciador de Projetos: Novo {escape(tipo)} em tarefa</h1>'
            f'<h2>Projeto: {escape(tarefa.projeto.titulo)}</h2>'
            f'<dl><dt>{rotulo}</dt><dd class="featured-info">{conteudo}</dd></dl>'
            f'{dados_gerais(tarefa)}'
        )
        send_notification(
            assunto=f'[SUAP] Gerenciador de Projetos: Novo {tipo} em tarefa',
            mensagem=mensagem,
            de=settings.DEFAULT_FROM_EMAIL,
            vinculos=[usuario.get_vinculo() for usuario in destinatarios],
        )

    @staticmethod
    def usuario_atribuido_a_tarefa(tarefa, usuario):
        if usuario == tl.get_user():
            return
        titulo = f'[SUAP] Gerenciador de Projetos: Tarefa #{tarefa.pk} atribuída a você'
        texto = []
        texto.append('<h1>Tarefa atribuída a você</h1>')
        texto.append(f'<h2>Projeto: {tarefa.projeto.titulo}</h2>')
        texto.append(f'<h3>#{tarefa.pk} {tarefa.titulo}</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Descrição da Tarefa:</dt><dd>{tarefa.descricao}</dd>')
        if tarefa.atribuido_por:
            texto.append(f'<dt>Atribuído por:</dt><dd>{tarefa.atribuido_por}</dd>')
        texto.append('</dl>')
        texto.append(dados_gerais(tarefa))
        send_notification(
            titulo,
            ''.join(texto),
            settings.DEFAULT_FROM_EMAIL,
            [
                usuario.get_vinculo(),
            ],
            categoria='Gerenciador de Projetos: Tarefa atribuída a você',
            objeto=tarefa,
        )

    @staticmethod
    def usuario_vinculado_a_projeto(projeto, usuario, tipo):
        if usuario == tl.get_user():
            return
        titulo = f'[SUAP] Gerenciador de Projetos: Você foi vinculado como {tipo} do projeto #{projeto.pk}'
        texto = []
        texto.append(f'<h1>Você foi vinculado como {tipo} de projeto</h1>')
        texto.append(f'<h2>Projeto: {projeto.titulo}</h2>')
        texto.append('<dl>')
        texto.append(f'<dt>Descrição do projeto:</dt><dd>{projeto.descricao}</dd>')
        if projeto.criado_por:
            texto.append(f'<dt>Criado por:</dt><dd>{projeto.criado_por}</dd>')
        texto.append('<dt>Criado em:</dt><dd>{}</dd>'.format(projeto.criado_em.strftime('%d/%m/%Y %H:%M')))
        texto.append('</dl>')
        url_projeto = urljoin(f'{settings.SITE_URL.rstrip("/")}/', projeto.get_absolute_url().lstrip('/'))
        texto.append(f'<p class="more-info">Para mais informações, acesse: <a href="{url_projeto}">{url_projeto}</a></p>')
        send_notification(
            titulo,
            ''.join(texto),
            settings.DEFAULT_FROM_EMAIL,
            [
                usuario.get_vinculo(),
            ],
            categoria='Gerenciador de Projetos: Projeto vinculado a você',
            objeto=projeto,
        )
