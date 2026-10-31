import datetime

from django.conf import settings

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from pafc.models import PAFC, RevisorTecnicoPAFC
from rh.models import Setor


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = datetime.datetime.today()

        # executar apenas na segunda-feira
        if hoje.weekday() == 0:
            revisores = RevisorTecnicoPAFC.objects.order_by('servidor_id').distinct('servidor_id')

            if revisores.exists():
                titulo = '[SUAP] e-PAFC: Pendência de Revisão Técnica'
                for revisor in revisores:
                    pafcs = PAFC.objects.filter(situacao=PAFC.AGUARDANDO_REVISAO_TECNICA, revisortecnicopafc__servidor=revisor.servidor).order_by(
                        'nome_curso'
                    )
                    if pafcs.exists():
                        mensagem = (
                            '<h1>Módulo e-PAFC</h1>'
                            '<h2>Pendência de Revisão Técnica</h2>'
                            '<p>Prezado revisor(a) técnico(a),</p>'
                            '<p>Você foi designado(a) para fazer a revisão técnica do PAFC (Projeto de Autorização de '
                            'Funcionamento de Curso) '
                        )
                        if pafcs.count() == 1:
                            pafc = pafcs.first()
                            mensagem += f'do Curso {pafc.nome_curso} do {pafc.get_nome_campus_normalizado()}.</p>'
                        else:
                            nomes_cursos_campus = [f'{pafc.nome_curso} do {pafc.get_nome_campus_normalizado()}' for pafc in pafcs]
                            mensagem += f'dos seguintes Cursos:</p><ul>   <li>{"</li><li>".join(nomes_cursos_campus)}</li></ul>'

                        ID_DIARE_IFRN = 1211
                        id_diare = Configuracao.get_valor_por_chave('pafc', 'setor_diare') or ID_DIARE_IFRN
                        diare = Setor.objects.suap_ativos().get(pk=id_diare)

                        mensagem += (
                            f'<p>Solicitamos que acesse o Suap e proceda com a revisão do PAFC através do caminho '
                            f'ENSINO &rarr; PAFC &rarr; PAFCs ou '
                            f'<a href="/admin/pafc/pafc/?situacao__exact={PAFC.AGUARDANDO_REVISAO_TECNICA}">clicando aqui</a>.</p>'
                            f'<p>Agradecemos a sua colaboração e lembramos que o bom andamento deste processo depende '
                            f'do empenho de todos(as) nós.</p>'
                            f'<p>Em caso de dúvidas, entrar em contato com a {diare.nome} ({diare.sigla}) através dos '
                            f'telefones: {diare.telefones(sem_ramal=True)}</p>'
                        )

                        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [revisor.servidor.get_vinculo()])
