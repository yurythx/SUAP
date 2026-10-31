"""Fluxo: os anexos do edital e dos projetos — cadastrar, editar, carregar o arquivo e remover.

Dois cadastros com nome parecido e papéis diferentes, na mesma tela do edital (abas "Anexos do
Edital" e "Anexos dos Projetos"): o primeiro é o documento que acompanha o edital (formulário,
modelo de plano), com arquivo; o segundo é o anexo que cada MEMBRO de projeto terá de enviar,
por tipo de membro e vínculo — é dele que nascem os ``ProjetoAnexo`` pendentes de cada equipe.
A regressão que se pega aqui é a do ciclo inteiro de cada um (os dois "Adicionar Anexo" da
mesma página, o popup de edição, a remoção por GET) e o upload do arquivo do membro.
"""

from uuid import uuid4

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAL = '/projetos/edital/{}/'
ADICIONAR_ANEXO_DO_EDITAL = '/projetos/adicionar_anexo_auxiliar/{}/'
EDITAR_ANEXO_DO_EDITAL = '/projetos/editar_anexo_auxiliar/{}/'
UPLOAD_ANEXO_DO_EDITAL = '/projetos/upload_anexo_auxiliar/{}/'
REMOVER_ANEXO_DO_EDITAL = '/projetos/remover_anexo_auxiliar/{}/'
ADICIONAR_ANEXO_DOS_PROJETOS = '/projetos/adicionar_anexo/{}/'
EDITAR_ANEXO_DOS_PROJETOS = '/projetos/editar_anexo/{}/'
REMOVER_ANEXO_DOS_PROJETOS = '/projetos/remover_anexo/{}/'
UPLOAD_ANEXO_DO_MEMBRO = '/projetos/upload_anexo/{}/'


def test_anexo_do_edital_ciclo_completo(logado_projetos, edital_novo):
    """Adicionar (popup) → editar (popup) → carregar arquivo → remover, pelo gerente."""
    from projetos.models import EditalAnexoAuxiliar

    edital = edital_novo()
    nome = f'Formulário {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba('Anexos do Edital')
    clicar_em(tela, ADICIONAR_ANEXO_DO_EDITAL.format(edital.pk))
    popup = popup_em(tela, ADICIONAR_ANEXO_DO_EDITAL.format(edital.pk))
    popup.preencher_formulario([('Nome', 'texto', nome), ('Descrição', 'textarea', 'Modelo de plano'), ('Ordem', 'número', '1')])
    tela = popup.salvar_no_popup('Salvar').sucesso('Anexo adicionado com sucesso.')
    anexo = EditalAnexoAuxiliar.objects.filter(edital=edital, nome=nome).first()
    assert anexo is not None, 'a UI disse que salvou, mas não persistiu'

    tela.clicar_aba('Anexos do Edital')
    clicar_em(tela, EDITAR_ANEXO_DO_EDITAL.format(anexo.pk))
    popup = popup_em(tela, EDITAR_ANEXO_DO_EDITAL.format(anexo.pk)).preencher('Descrição', 'textarea', 'Modelo de plano revisado')
    tela = popup.salvar_no_popup('Salvar').sucesso('Anexo editado com sucesso.')
    anexo.refresh_from_db()
    assert anexo.descricao == 'Modelo de plano revisado', 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba('Anexos do Edital')
    clicar_em(tela, UPLOAD_ANEXO_DO_EDITAL.format(anexo.pk))
    tela.esperar().ver_titulo('Upload de Arquivo').preencher('Arquivo', 'arquivo', 'arquivo.pdf').clicar_botao('Enviar')
    tela.esperar().sucesso('Arquivo enviado com sucesso.')
    anexo.refresh_from_db()
    assert anexo.arquivo_id is not None, 'a UI disse que enviou, mas o anexo segue sem arquivo'

    tela.clicar_aba('Anexos do Edital')
    clicar_em(tela, REMOVER_ANEXO_DO_EDITAL.format(anexo.pk))
    tela.esperar().sucesso('Anexo removido com sucesso.')
    assert not EditalAnexoAuxiliar.objects.filter(pk=anexo.pk).exists(), 'a UI disse que removeu, mas o anexo continua'


def test_anexo_dos_projetos_ciclo_completo(logado_projetos, edital_novo):
    """Adicionar (tela própria) → editar (popup) → remover — o anexo que cada membro enviará."""
    from projetos.models import EditalAnexo

    edital = edital_novo()
    nome = f'Termo {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba('Anexos dos Projetos')
    clicar_em(tela, ADICIONAR_ANEXO_DOS_PROJETOS.format(edital.pk))
    tela.esperar().ver_titulo('Adicionar Anexo').preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('Descrição', 'textarea', 'Termo de compromisso do aluno'),
            ('Tipo de Membro', 'lista', 'Aluno'),
            ('Tipo de Vínculo', 'lista', 'Voluntário'),
            ('Ordem', 'número', '1'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Anexo adicionado com sucesso.')
    anexo = EditalAnexo.objects.filter(edital=edital, nome=nome).first()
    assert anexo is not None, 'a UI disse que salvou, mas não persistiu'
    assert anexo.tipo_membro == EditalAnexo.ALUNO, f'tipo de membro gravado: {anexo.tipo_membro}'

    tela.clicar_aba('Anexos dos Projetos')
    clicar_em(tela, EDITAR_ANEXO_DOS_PROJETOS.format(anexo.pk))
    popup = popup_em(tela, EDITAR_ANEXO_DOS_PROJETOS.format(anexo.pk)).preencher('Tipo de Vínculo', 'lista', 'Bolsista')
    tela = popup.salvar_no_popup('Salvar').sucesso('Anexo editado com sucesso.')
    anexo.refresh_from_db()
    assert anexo.vinculo == EditalAnexo.BOLSISTA, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba('Anexos dos Projetos')
    clicar_em(tela, REMOVER_ANEXO_DOS_PROJETOS.format(anexo.pk))
    tela.esperar().sucesso('Anexo removido com sucesso.')
    assert not EditalAnexo.objects.filter(pk=anexo.pk).exists(), 'a UI disse que removeu, mas o anexo continua'


def test_colaborador_externo_nao_pode_ser_bolsista(logado_projetos, edital_novo):
    """Regra do ``EditalAnexoForm.clean``: anexo de colaborador externo como bolsista é recusado."""
    from projetos.models import EditalAnexo

    edital = edital_novo()
    nome = f'Termo externo {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(ADICIONAR_ANEXO_DOS_PROJETOS.format(edital.pk))
    tela.preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('Tipo de Membro', 'lista', 'Colaborador Externo'),
            ('Tipo de Vínculo', 'lista', 'Bolsista'),
            ('Ordem', 'número', '1'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.erro('Os colaboradores externos não podem ser cadastrados como bolsistas.')
    assert not EditalAnexo.objects.filter(edital=edital, nome=nome).exists(), 'o formulário recusou, mas o anexo foi gravado'


def test_membro_envia_o_arquivo_do_anexo_do_projeto(logado_projetos, anexo_do_membro):
    """O coordenador do projeto em edição carrega o arquivo de um anexo pendente da equipe."""
    anexo = anexo_do_membro
    tela = Tela(logado_projetos('coordenador_projeto')).ir(UPLOAD_ANEXO_DO_MEMBRO.format(anexo.pk))

    tela.ver_titulo('Upload de Arquivo').preencher('Arquivo', 'arquivo', 'arquivo.pdf').clicar_botao('Enviar')
    tela.esperar().sucesso('Arquivo enviado com sucesso.')
    anexo.refresh_from_db()
    assert anexo.arquivo_id is not None, 'a UI disse que enviou, mas o anexo segue sem arquivo'
