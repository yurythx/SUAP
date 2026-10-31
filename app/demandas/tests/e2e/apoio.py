"""Auxiliares compartilhados pelos e2e do Demandas.

Só o que **mais de um arquivo** precisa; o resto fica no próprio teste.
"""

from __future__ import annotations

from playwright.sync_api import expect

from djtools.e2e_ui import Tela


def esperar_editor_rico(tela: Tela, campo_id: str) -> None:
    """Espera o TinyMCE do campo ficar pronto **antes** de preencher.

    O editor inicializa em async e reescreve o `body` do iframe (e o `textarea`) quando
    termina: preencher antes disso deixa o campo vazio no submit e a tela não acusa erro — o
    servidor é que recusa por campo obrigatório. O sintoma só aparece com o banco frio, onde
    o JS não vem do cache.
    """
    tela.pagina.wait_for_function(
        '(id) => { const editor = window.tinymce?.get?.(id); return !!editor && editor.initialized === true }',
        arg=campo_id,
    )


def marcar_modulo(tela: Tela, nome: str) -> None:
    """Marca o módulo (tag) no formulário de demanda, que recarrega a lista por AJAX.

    O `demanda_form.js` dispara **dois** carregamentos ao escolher a área (`select2:select` e
    `change`) e o segundo substitui a lista inteira: marcar entre os dois apaga a marcação e o
    admin recusa o formulário por campo obrigatório — falha que aparece longe da causa (na
    mensagem de sucesso) e só sob carga. Por isso a marcação é reafirmada até ficar estável.
    """
    from demandas.models import Tag

    tag = Tag.objects.get(nome=nome)
    alvo = tela.loc(f'//input[@name="tags" and @value="{tag.pk}"]')
    for _ in range(4):
        if alvo.count():
            alvo.first.check()
        try:
            expect(alvo.first).to_be_checked(timeout=1500)
            return
        except AssertionError:
            continue
    raise AssertionError(f'não foi possível marcar o módulo {nome!r}: a lista é recarregada por AJAX')
