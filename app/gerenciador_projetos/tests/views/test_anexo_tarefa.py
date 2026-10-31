"""Testa a notificação ao anexar um arquivo à tarefa."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gerenciador_projetos.models import Projeto, Tarefa
from rh.models import UnidadeOrganizacional
from rh.tests.factories import ServidorFactory


class TestAnexoTarefa:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)

    def test_notifica_novo_anexo_sem_notificar_autor(self, client, mailoutbox) -> None:
        tarefa = self._tarefa()
        servidor_destinatario = ServidorFactory(setor=self.setor)
        destinatario = servidor_destinatario.get_user()
        vinculo_destinatario = servidor_destinatario.get_vinculo()
        vinculo_destinatario.email_pessoal = f'{servidor_destinatario.matricula}@mail.gov'
        vinculo_destinatario.save(update_fields=['email_pessoal'])
        tarefa.atribuido_a.add(destinatario)
        quantidade_anterior = len(mailoutbox)
        client.force_login(self.user_admin)

        arquivo = SimpleUploadedFile('relatorio.pdf', b'%PDF-1.4 arquivo de teste', content_type='application/pdf')
        client.post(reverse('adicionar_anexo', args=[tarefa.pk]), {'anexo': arquivo})

        assert len(mailoutbox) == quantidade_anterior + 1
        assert f'{servidor_destinatario.matricula}@mail.gov' in mailoutbox[-1].to
        assert f'{self.admin.get_vinculo().email_pessoal}' not in mailoutbox[-1].to
        assert 'novo anexo' in mailoutbox[-1].subject.lower()
