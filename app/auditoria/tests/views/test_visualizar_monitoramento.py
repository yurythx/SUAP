"""Issue #17802 (Sentry SUAP-WX1): aluno logado abrindo ``/auditoria/monitoramento/<id>/``
derrubava a view com ``AttributeError: 'Aluno' object has no attribute
'eh_chefe_do_setor_hoje'`` — ``tenho_poder_de_chefe`` assumia que o relacionamento do
usuário era um servidor. Quem não é chefe (nem designado) deve ter o acesso negado.
"""

from __future__ import annotations

from django.urls import reverse

from edu.tests.factories import AlunoFactory


class TestVisualizarMonitoramento:
    def test_aluno_tem_acesso_negado_sem_erro(self, cenario_atendimento):
        c = cenario_atendimento
        aluno_user = AlunoFactory().get_user()

        c.client.force_login(aluno_user)
        resp = c.client.get(reverse('auditoria:visualizar_monitoramento', kwargs={'monitoramento_id': c.monitoramento.id}))

        # A view nega com redirect + mensagem de erro (padrão do módulo), sem renderizar o monitoramento.
        assert resp.status_code == 302
        mensagens = [str(m) for m in resp.wsgi_request._messages]
        assert 'Você não tem permissão para realizar essa ação.' in mensagens
