import tempfile
from datetime import date, datetime

from django.conf import settings
from django.core import signing

from djtools.utils import generate_pdf, merge_pdf_files, send_mail, send_notification


def anexar_tabela_trabalhos_aprovados(submissoes_aprovadas, certificado):
    """
    Adiciona uma tabela em PDF ao certificado caso o parâmetro #ANEXARTRABALHOSAPROVADOS# esteja presente.

    :param participante: Objeto do participante
    :param caminho_arquivo: Caminho do arquivo original do certificado
    :return: Caminho do novo arquivo com a tabela anexada
    """
    with tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False) as tabela_submissao_pdf:
        tabela_submissao_pdf.write(generate_pdf(template_name='tabela_submissao_pdf.html', context=submissoes_aprovadas).getvalue())
        tabela_submissao_pdf.close()

    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(merge_pdf_files([certificado, tabela_submissao_pdf.name]))
    tmp.close()
    return tmp.name


class ExibirMensagem:
    @staticmethod
    def convite_aceito(participante):
        conteudo = []
        conteudo.append(f'<p>Sr(a). {participante.nome},</p>')
        conteudo.append('<p>Agradecemos o seu aceite.</p>')
        if participante.tipo.eh_avaliador_de_trabalho():
            texto_complementar = 'de avaliações'
        else:
            texto_complementar = 'privada para complementar informações do seu perfil'
        conteudo.append(f'<p>Em breve você receberá uma notificação por e-mail com as informações para acesso à área {texto_complementar}.</p>')
        return ''.join(conteudo)

    @staticmethod
    def convite_recusado(participante):
        conteudo = []
        tipo_participacao = 'avaliador' if participante.tipo.eh_avaliador_de_trabalho() else 'convidado'
        conteudo.append(f'<p>Sr(a). {participante.nome},</p>')
        conteudo.append(f'<p>Agradecemos por nos informar de sua indisponibilidade de participar como {tipo_participacao} de nosso evento.</p>')
        conteudo.append('<p>Esperamos poder contar com a sua participação em uma próxima oportunidade.</p>')
        return ''.join(conteudo)


class Notificar:
    @staticmethod
    def enviar_certificado_evento(participante):
        evento = participante.evento
        conteudo = []
        conteudo.append('<h1>Certificação de Participação</h1>')
        conteudo.append(f'<h2>{evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
        conteudo.append(f'<p>Para gerar o seu certificado de participação no evento "{evento.nome}", acesse:</p>')
        conteudo.append(f'<p><a href="{participante.get_url_download_certificado()}">Certificado de Participação no Evento</a></p>')

        for atividade in participante.get_atividades():
            url_atividade = participante.get_url_download_certificado(atividade.id)
            conteudo.append(f'<p><a href="{url_atividade}">Certificado de Participação - {atividade}</a></p>')

        send_mail(
            f'[SUAP] Certificado de Participação - {evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            [participante.email],
        )

    @staticmethod
    def inscricao_no_evento(evento, participante):
        attachments = []
        conteudo = []
        url = f'{settings.SITE_URL}/eventos/inscricao/1/{evento.id}/'
        url_area_do_participante = f'{settings.SITE_URL}/eventos/area_do_participante/{evento.pk}/'
        conteudo.append('<h1>Confirmação de inscrição em evento</h1>')
        conteudo.append(f'<h2>{evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
        conteudo.append(f'<p>Sua inscrição no evento <strong>{evento.nome}</strong> foi <strong>confirmada</strong>.</p>')
        conteudo.append(
            f'<p>Para acessar a área privativa do participante, você deve acessar o endereço: <a href="{url_area_do_participante}">{url_area_do_participante}</a>, informar o seu <b>e-mail</b> e a seguinte chave de acesso: <b>{participante.chave_acesso}</b></p>'
        )

        if evento.utilizar_qr_code:
            qr_code_path = participante.gerar_qr_code()
            arquivo = open(qr_code_path.name, 'rb')
            anexo = arquivo.read()
            attachments = [('QRCode.png', anexo, 'image/png')]
            conteudo.append('<p>Você está recebendo seu QR Code para credenciamento e confirmação de presença.</p>')
            conteudo.append('<p>Este código é pessoal e intransferível. Salve-o ou imprima-o e leve com você para o evento.</p>')
            conteudo.append(
                '<p>Será necessário apresentar esse código à equipe de credenciamento ou responsáveis pelos acessos às atividades do evento.</p>'
            )

        conteudo.append('<p>Agradecemos a sua participação e desejamos sucesso no evento!</p>')
        conteudo.append(f'<p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>')

        send_mail(
            '[SUAP] Confirmação de inscrição em evento',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            [participante.email],
            fail_silently=False,
            attachments=attachments,
        )

    @staticmethod
    def enviar_qrcode_participante(participante):
        qr_code_path = participante.gerar_qr_code()
        arquivo = open(qr_code_path.name, 'rb')
        anexo = arquivo.read()
        attachments = [('QRCode.png', anexo, 'image/png')]
        url_area_do_participante = f'{settings.SITE_URL}/eventos/area_do_participante/{participante.evento.pk}/'

        conteudo = []
        conteudo.append('<h1>QR Code de participante em evento</h1>')
        conteudo.append(f'<h2>{participante.evento.nome}</h2>')
        conteudo.append('<p>Você está recebendo seu QR Code para credenciamento e confirmação de presença.</p>')
        conteudo.append('<p>Este código é pessoal e intransferível. Salve-o ou imprima-o e leve com você para o evento.</p>')
        conteudo.append(
            '<p>Será necessário apresentar esse código à equipe de credenciamento ou responsáveis pelos acessos às atividades do evento.</p>'
        )
        conteudo.append(
            f'<p>Para acessar a área privativa do participante, você deve acessar o endereço: <a href="{url_area_do_participante}">{url_area_do_participante}</a>, informar o seu <b>e-mail</b> e a seguinte chave de acesso: <b>{participante.chave_acesso}</b></p>'
        )

        conteudo.append('<p>Agradecemos a sua participação e desejamos sucesso no evento!</p>')
        send_mail(
            '[SUAP] QR Code de participante em evento',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            [participante.email],
            fail_silently=False,
            attachments=attachments,
        )

    @staticmethod
    def confirmar_presenca_por_link_em_evento(evento, participante):
        hash = signing.dumps({'participante_id': participante.id})
        url = f'{settings.SITE_URL}/eventos/confirmar_presenca_por_link/{evento.id}/{participante.id}?hash={hash}'
        conteudo = []
        conteudo.append('<h1>Confirmação de Presença em Evento</h1>')
        conteudo.append(f'<h2>{evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
        conteudo.append('<p>Espero que esta mensagem o(a) encontre bem.</p>')
        conteudo.append(f'<p>Estamos entrando em contato para lembrá-lo(a) sobre o evento <b>"{evento.nome}"</b>, que acontecerá em breve.</p>')
        conteudo.append(f'<p>Para confirmar sua participação no evento, pedimos que acesse o link a seguir: <a href="{url}">{url}</a>.</p>')
        conteudo.append('<p>Agradecemos antecipadamente pela sua confirmação.</p>')
        send_mail('[SUAP] Confirmação de Presença em Evento', ''.join(conteudo), settings.DEFAULT_FROM_EMAIL, [participante.email])

    @staticmethod
    def confirmar_presenca_por_link_em_atividade(atividade, participante):
        hash = signing.dumps({'participante_id': participante.id, 'timestamp': datetime.now().timestamp()})
        url = f'{settings.SITE_URL}/eventos/confirmar_presenca_por_link_atividade/{atividade.id}/{participante.id}?hash={hash}'
        conteudo = []
        conteudo.append('<h1>Confirmação de Presença em Atividade de Evento</h1>')
        conteudo.append(f'<h2>{atividade.descricao} / {atividade.evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
        conteudo.append('<p>Espero que esta mensagem o(a) encontre bem.</p>')
        conteudo.append(
            f'<p>Estamos entrando em contato para lembrá-lo(a) sobre a atividade <b>"{atividade.descricao}"</b> do evento "{atividade.evento.nome}", que acontecerá em breve.</p>'
        )
        conteudo.append(f'<p>Para confirmar sua participação na atividade, pedimos que acesse o link a seguir: <a href="{url}">{url}</a>.</p>')
        conteudo.append(
            '<p><strong>IMPORTANTE:</strong> Este link é válido por apenas <strong>1 hora</strong> a partir do recebimento deste email. Caso expire, o organizador do evento poderá reenviar o email e o link será renovado.</p>'
        )
        conteudo.append('<p>Agradecemos antecipadamente pela sua confirmação.</p>')
        send_mail('[SUAP] Confirmação de Presença em Atividade de Evento', ''.join(conteudo), settings.DEFAULT_FROM_EMAIL, [participante.email])

    @staticmethod
    def notificar_acesso(evento, participante):
        url = f'{settings.SITE_URL}/eventos/autenticar_participante/{evento.pk}/'
        conteudo = []
        if participante.tipo.eh_avaliador_de_trabalho():
            assunto = '[SUAP] Avaliador de trabalhos'
            conteudo.append('<h1>Acesso do avaliador</h1>')
            conteudo.append(f'<h2>{evento.nome}</h2>')
            conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
            conteudo.append(f'<p>Você foi selecionado como avaliador de trabalhos do evento: {evento.nome}.</p>')
            if participante.avaliadormodalidade_set.exists():
                conteudo.append('<p>Modalidades e areas temáticas vinculadas ao seu perfil:</p>')
                conteudo.append('<ul>')
                for avaliador_modalidade in participante.avaliadormodalidade_set.all():
                    areas_tematicas = ', '.join(avaliador_modalidade.areas_tematicas.all().values_list('titulo', flat=True))
                    conteudo.append(
                        f'<li><b>{avaliador_modalidade.modalidade.tipo.titulo}</b>, para a(s) área(s) temática(s) de <b>{areas_tematicas}</b>.</li>'
                    )
                conteudo.append('</ul>')
            conteudo.append(
                f'<p>Para realizar as avaliações, você deve acessar o endereço: <a href="{url}">{url}</a>, informar o seu <b>e-mail</b> e a seguinte chave de acesso: <b>{participante.chave_acesso}</b></p>'
            )
            hoje = date.today()
            proxima_avaliacao = evento.fluxos_submissao.filter(etapa='AVA', data_fim__gte=hoje).order_by('data_inicio').first()
            if proxima_avaliacao:
                data_inicio = proxima_avaliacao.data_inicio.strftime('%d/%m/%Y')
                data_fim = proxima_avaliacao.data_fim.strftime('%d/%m/%Y')
                conteudo.append(f'<p>O período de avaliações vai de {data_inicio} a {data_fim}.</p>')

        elif participante.tipo.eh_convidado():
            assunto = '[SUAP] Convidado de atividades'
            conteudo.append('<h1>Acesso do convidado</h1>')
            conteudo.append(f'<h2>{evento.nome}</h2>')
            conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
            conteudo.append(f'<p>Você foi selecionado como convidado de atividades do evento: {evento.nome}.</p>')
            if participante.atividades.exists():
                conteudo.append('<p>Atividades vinculadas:</b>.')
                for atividade in participante.atividades.all():
                    conteudo.append(f'<p>{atividade}</b>.')
            conteudo.append(
                f'<p>Para atualizar seu perfil, você deve acessar o endereço: <a href="{url}">{url}</a>, informar o seu <b>e-mail</b> e a seguinte chave de acesso: <b>{participante.chave_acesso}</b></p>'
            )
        else:
            assunto = '[SUAP] Participante de atividades'
            conteudo.append('<h1>Acesso do participante</h1>')
            conteudo.append(f'<h2>{evento.nome}</h2>')
            conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
            conteudo.append('<p>Espero que esta mensagem o(a) encontre bem.</p>')
            conteudo.append(f'<p>Estamos entrando em contato para lembrá-lo(a) sobre o evento <b>"{evento.nome}"</b>, que acontecerá em breve.</p>')
            conteudo.append(
                f'<p>Para se inscrever nas atividades do evento, você deve acessar o endereço: <a href="{url}">{url}</a>, informar o seu <b>e-mail</b> e a seguinte chave de acesso: <b>{participante.chave_acesso}</b></p>'
            )

        conteudo.append('<p>--</p>')
        conteudo.append('<p>Agradecemos a sua participação e desejamos sucesso no evento!</p>')

        send_mail(assunto, ''.join(conteudo), settings.DEFAULT_FROM_EMAIL, [participante.email])

    @staticmethod
    def enviar_avaliacao_evento(evento, participante):
        url_responder = f'{settings.SITE_URL}/eventos/responder_avaliacao/{evento.pk}/?email={participante.email}'
        url_autenticar = f'{settings.SITE_URL}/eventos/autenticar_participante/{evento.pk}/?email={participante.email}'
        conteudo = []
        conteudo.append('<h1>Avaliação do evento</h1>')
        conteudo.append(f'<h2>{evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
        conteudo.append('<p>A sua opinião é importante para aprimorarmos as próximas edições do evento.</p>')
        conteudo.append(
            f'<p>Para responder, acesse: <a href="{url_responder}">{url_responder}</a>. '
            f'Caso seja solicitado, utilize seu e-mail e a chave de acesso <b>{participante.chave_acesso}</b>.</p>'
        )
        conteudo.append(f'<p>Você também pode acessar a área do participante por: <a href="{url_autenticar}">{url_autenticar}</a>.</p>')
        conteudo.append('<p>Obrigado por participar.</p>')
        send_mail(f'[SUAP] Avaliação do Evento - {evento.nome}', ''.join(conteudo), settings.DEFAULT_FROM_EMAIL, [participante.email])

    @staticmethod
    def enviar_avaliacao_pendente_para_liberacao_certificado(evento, participante):
        url_responder = f'{settings.SITE_URL}/eventos/responder_avaliacao/{evento.pk}/?email={participante.email}'
        url_autenticar = f'{settings.SITE_URL}/eventos/autenticar_participante/{evento.pk}/?email={participante.email}'
        conteudo = []
        conteudo.append('<h1>Avaliação necessária para emissão do certificado</h1>')
        conteudo.append(f'<h2>{evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
        conteudo.append(
            '<p>Identificamos que o seu certificado ainda não pode ser liberado, pois este evento exige o preenchimento da avaliação pós-evento.</p>'
        )
        conteudo.append(
            f'<p>Para responder a avaliação e liberar a emissão do certificado, acesse: <a href="{url_responder}">{url_responder}</a>.</p>'
        )
        conteudo.append(
            f'<p>Caso seja solicitado, utilize seu e-mail e a chave de acesso <b>{participante.chave_acesso}</b>. '
            f'Você também pode acessar a área do participante por: <a href="{url_autenticar}">{url_autenticar}</a>.</p>'
        )
        conteudo.append('<p>Após o envio da avaliação, o certificado poderá ser emitido conforme as regras do evento.</p>')
        send_mail(
            f'[SUAP] Avaliação necessária para liberar certificado - {evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            [participante.email],
        )

    @staticmethod
    def convidar_participante(evento, participante, tipo_participante):
        hash_assinado = signing.dumps({'participante_id': participante.id})
        url_aceitar = f'{settings.SITE_URL}/eventos/aceitar_convite/{evento.pk}/{participante.id}/{hash_assinado}/'
        url_recusar = f'{settings.SITE_URL}/eventos/recusar_convite/{evento.pk}/{participante.id}/{hash_assinado}/'
        conteudo = []
        if tipo_participante.eh_avaliador_de_trabalho():
            assunto = '[SUAP] Convite para avaliação de trabalhos'
            conteudo.append('<h1>Convite para avaliação de trabalhos</h1>')
            conteudo.append(f'<h2>{evento.nome}</h2>')
            conteudo.append(f'<p>A(o) Exmo(a). Sr(a). {participante.nome},</p>')
            conteudo.append(
                f'<p>Solicitamos a sua colaboração na avaliação do mérito científico dos trabalhos submetidos ao evento <b>{evento.nome}</b>.'
            )
            conteudo.append('<p>A identidade do avaliador de trabalhos é mantida em sigilo.</p>')
        else:
            assunto = '[SUAP] Convite para colaboração em atividade de Evento'
            conteudo.append('<h1>Convite para colaboração em atividade de Evento</h1>')
            conteudo.append(f'<h2>{evento.nome}</h2>')
            conteudo.append(f'<p>A(o) Exmo(a). Sr(a). {participante.nome},</p>')
            conteudo.append(f'<p>Solicitamos a valiosa colaboração de V.Sa. na realização de atividades no evento <b>{evento.nome}</b>.')
            if participante.atividades.exists():
                conteudo.append('<p><strong>Atividades vinculadas:</strong></p>.')
                conteudo.append('<ul>')
                for atividade in participante.atividades.all():
                    conteudo.append(f'<li>{atividade}</li>.')
                conteudo.append('</ul>')

        conteudo.append('<p>Para responder, acesse uma das opções abaixo:</p>')
        conteudo.append(f'<p><a href="{url_aceitar}">Aceitar convite</a></p>')
        conteudo.append('<p>ou</p>')
        conteudo.append(f'<p><a href="{url_recusar}">Recusar convite</a></p>')
        conteudo.append('<p>Expressamos nesta oportunidade, os sinceros agradecimentos pela atenção dispensada ao nosso convite.</p>')

        send_mail(assunto, ''.join(conteudo), settings.DEFAULT_FROM_EMAIL, [participante.email])

    @staticmethod
    def comprovante_de_submissao(submissao):
        autores = ', '.join([participante.nome for participante in submissao.autores])
        emails = [participante.email for participante in submissao.autores]
        conteudo = []
        conteudo.append('<h1>Comprovante de Submissão</h1>')
        conteudo.append(f'<h2>{submissao.evento.nome}</h2>')
        conteudo.append(f'<p>O trabalho abaixo foi submetido com sucesso ao evento <strong>{submissao.evento.nome}</strong>:')
        conteudo.append('<dl>')
        conteudo.append(f'<dt>Título:</dt><dd>{submissao.titulo}</dd>')
        conteudo.append(f'<dt>Data de subsmissão:</dt><dd>{submissao.data_hora.strftime("%d/%m/%Y %H:%M")}</dd>')
        conteudo.append(f'<dt>Modalidade:</dt><dd>{submissao.modalidade.tipo.titulo}</dd>')
        conteudo.append(f'<dt>Área temática:</dt><dd>{submissao.area_tematica.titulo}</dt>')
        conteudo.append(f'<dt>Autores:</dt><dd>{autores}</dd>')
        conteudo.append('</dl>')
        conteudo.append('<p>Cordialmente,</p>')
        conteudo.append('<p>Comissão do evento</p>')

        send_mail(f'[SUAP] Comprovante de Submissão no Evento: {submissao.evento.nome}', ''.join(conteudo), settings.DEFAULT_FROM_EMAIL, emails)

    @staticmethod
    def trabalhos_aprovados(submissao):
        autores = ', '.join([participante.nome for participante in submissao.autores])
        emails = [participante.email for participante in submissao.autores]
        conteudo = []
        conteudo.append('<h1>Notificação de trabalho aprovado em evento</h1>')
        conteudo.append(f'<h2>{submissao.modalidade.evento.nome}</h2>')
        conteudo.append('<p>Caro(a) autor(a),</p>')
        conteudo.append(
            f'<p>Parabéns! O trabalho intitulado <b>{submissao.titulo}</b> de autoria de <b>{autores}</b>, '
            f'foi aprovado no evento <b>{submissao.modalidade.evento.nome}</b>, por atender aos critérios do edital de seleção.</p>'
        )
        conteudo.append('<dl>')
        conteudo.append(f'<dt>Modalidade:</dt><dd>{submissao.modalidade.tipo.titulo}</dd>')
        conteudo.append(f'<dt>Área temática:</dt><dd>{submissao.area_tematica.titulo}</dd>')
        conteudo.append('</dl>')

        conteudo.append('<p>Aguardamos pela presença de seus autores em nosso evento.</p>')
        send_mail(
            f'[SUAP] Notificação de trabalho aprovado no Evento: {submissao.modalidade.evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            emails,
        )

    @staticmethod
    def trabalhos_reprovados(submissao):
        emails = [participante.email for participante in submissao.autores]
        conteudo = [
            '<h1>Notificação de trabalho reprovado em evento</h1>',
            f'<h2>{submissao.modalidade.evento.nome}</h2>',
            '<p>Caro(a) autor(a),</p>',
            (
                f'<p>Com nossos respeitosos cumprimentos, lamentamos informar que o trabalho intitulado '
                f'<b>{submissao.titulo}</b> não foi aprovado no evento <b>{submissao.modalidade.evento.nome}</b>.</p>'
            ),
            '<p>Agradecemos o envio do mesmo e esperamos poder contar com suas contribuições acadêmicas/gerenciais em uma outra oportunidade.</p>',
        ]

        send_mail(
            f'[SUAP] Notificação de trabalho reprovado no Evento: {submissao.modalidade.evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            emails,
        )

    @staticmethod
    def trabalho_removido_duplicidade(submissao):
        """
        Notifica os autores sobre a remoção da submissão por duplicidade.
        """
        emails = [participante.email for participante in submissao.autores if participante.email]
        if not emails:
            return

        autores = ', '.join([participante.nome for participante in submissao.autores])
        conteudo = [
            '<h1>Notificação de Remoção de Trabalho por Duplicidade</h1>',
            f'<h2>{submissao.modalidade.evento.nome}</h2>',
            '<p>Caro(a) autor(a),</p>',
            (
                f'<p>Informamos que o trabalho intitulado <b>{submissao.titulo}</b>, de autoria de <b>{autores}</b>, '
                f'foi removido da análise do evento <b>{submissao.modalidade.evento.nome}</b> por ter sido identificado como duplicidade.</p>'
            ),
            '<h3>Motivo da Remoção:</h3>',
            f'<p>{submissao.motivo_remocao}</p>',
            '<p><b>Informações da Submissão:</b></p>',
            '<ul>',
            f'<li><b>Modalidade:</b> {submissao.modalidade.tipo.titulo}</li>',
            f'<li><b>Área Temática:</b> {submissao.area_tematica.titulo}</li>',
            f'<li><b>Data de Submissão:</b> {submissao.data_hora.strftime("%d/%m/%Y às %H:%M")}</li>',
            '</ul>',
            '<p>Caso você acredite que houve um erro na identificação de duplicidade, entre em contato com a coordenação do evento.</p>',
            '<p>Agradecemos pela compreensão.</p>',
        ]

        send_mail(
            f'[SUAP] Trabalho Removido por Duplicidade - {submissao.modalidade.evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            emails,
        )

    @staticmethod
    def solicitacao_correcoes(versao):
        submissao = versao.submissao
        autores = ', '.join([participante.nome for participante in submissao.autores])
        emails = [participante.email for participante in submissao.autores]
        conteudo = []
        conteudo.append('<h1>Solicitação de Correções no Trabalho Submetido</h1>')
        conteudo.append(f'<h2>{submissao.modalidade.evento.nome}</h2>')
        conteudo.append('<p>Caro(a) autor(a),</p>')
        conteudo.append(
            f'<p>O trabalho intitulado <b>{submissao.titulo}</b>, de autoria de <b>{autores}</b>, submetido ao evento <b>{submissao.modalidade.evento.nome}</b>, '
            f'foi avaliado e necessita de correções para atender aos critérios estabelecidos.</p>'
        )

        comentarios = [avaliacao for avaliacao in versao.pareceres.all() if avaliacao.observacao]
        if comentarios:
            conteudo.append('<p>Segue abaixo os comentários do(s) avaliador(es) para orientar as correções necessárias:</p>')
            for index, avaliacao in enumerate(comentarios, start=1):
                conteudo.append(f'<p><b>Avaliador #{index}</b>: {avaliacao.observacao}</p>')

        conteudo.append('<p>Pedimos que realize as correções solicitadas e submeta novamente o trabalho dentro do prazo estipulado.</p>')
        conteudo.append('<p>Agradecemos pela sua contribuição e estamos à disposição para quaisquer dúvidas.</p>')

        send_mail(
            f'[SUAP] Solicitação de correções no trabalho submetido: {submissao.modalidade.evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            emails,
        )

    @staticmethod
    def trabalho_aprovado_para_avaliacao_presencial(submissao):
        autores = ', '.join([participante.nome for participante in submissao.autores])
        emails = [participante.email for participante in submissao.autores]
        conteudo = []
        conteudo.append('<h1>Trabalho aprovado para avaliação presencial</h1>')
        conteudo.append(f'<h2>{submissao.modalidade.evento.nome}</h2>')
        conteudo.append('<p>Caro(a) autor(a),</p>')
        conteudo.append(
            f'<p>Temos o prazer de informar que o trabalho intitulado <b>{submissao.titulo}</b>, de autoria de <b>{autores}</b>, foi aprovado para a etapa de avaliação presencial no evento <b>{submissao.modalidade.evento.nome}</b>.</p>'
        )
        conteudo.append('<p>Nesta etapa, não é necessário realizar nenhuma correção no trabalho submetido.</p>')
        conteudo.append('<p>Agradecemos pela sua participação e desejamos sucesso no evento!</p>')
        conteudo.append('<p>Cordialmente,</p>')
        conteudo.append('<p>Comissão Organizadora do Evento</p>')

        send_mail(
            f'[SUAP] Trabalho aprovado para avaliação presencial: {submissao.modalidade.evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            emails,
        )

    @staticmethod
    def pendencias_do_avaliador(avaliador, versoes_pendentes):
        url = f'{settings.SITE_URL}/eventos/autenticar_participante/{avaliador.evento.pk}/'
        conteudo = []
        conteudo.append('<h1>Notificação de Pendências de Avaliação</h1>')
        conteudo.append(f'<h2>{avaliador.evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {avaliador.nome},</p>')
        conteudo.append(
            f'<p>Estamos entrando em contato para lembrá-lo(a) sobre as pendências de avaliação de trabalhos submetidos ao evento <b>{avaliador.evento.nome}</b>.</p>'
        )
        conteudo.append('<p>Segue abaixo a lista de trabalhos pendentes para avaliação:</p>')
        conteudo.append('<ul>')
        for versao in versoes_pendentes:
            conteudo.append(f'<li><b>{versao.submissao.titulo}</b></li>')
        conteudo.append('</ul>')
        conteudo.append('<p>Pedimos que realize as avaliações o mais breve possível, dentro do prazo estipulado.</p>')
        conteudo.append(
            f'<p>Para realizar as avaliações, você deve acessar o endereço: <a href="{url}">{url}</a>, informar o seu <b>e-mail</b> e a seguinte chave de acesso: <b>{avaliador.chave_acesso}</b></p>'
        )
        conteudo.append('<p>Agradecemos pela sua colaboração e estamos à disposição para quaisquer dúvidas.</p>')
        conteudo.append('<p>Cordialmente,</p>')
        conteudo.append('<p>Comissão Organizadora do Evento</p>')

        send_mail(
            f'[SUAP] Pendências de avaliação no evento: {avaliador.evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            [avaliador.email],
        )

    @staticmethod
    def coordenadores_pendencias_dos_avaliadores(evento, pendencias_por_avaliador):
        conteudo = []
        conteudo.append('<h1>Notificação de Pendências de Avaliação</h1>')
        conteudo.append(f'<h2>{evento.nome}</h2>')
        conteudo.append('<p>Prezado(a) Coordenador(a),</p>')
        conteudo.append(
            f'<p>Estamos entrando em contato para informar sobre as pendências de avaliação de trabalhos submetidos ao evento <b>{evento.nome}</b>.</p>'
        )
        conteudo.append('<p>Segue abaixo a lista de avaliadores com pendências:</p>')
        conteudo.append('<ul>')
        for avaliador, quantidade in pendencias_por_avaliador.items():
            conteudo.append(f'<li><b>{avaliador.nome}</b>: {quantidade} avaliações pendentes.</li>')
        conteudo.append('</ul>')
        conteudo.append(
            '<p>Pedimos que entre em contato com os avaliadores para garantir que as avaliações sejam realizadas dentro do prazo estipulado.</p>'
        )
        conteudo.append('<p>Agradecemos pela sua colaboração e estamos à disposição para quaisquer dúvidas.</p>')
        conteudo.append('<p>Cordialmente,</p>')
        conteudo.append('<p>Coordenação Sistêmica de Eventos</p>')

        send_notification(
            f'[SUAP] Pendências de avaliação no evento: {evento.nome}',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            [evento.coordenador.get_vinculo()],
        )

    @staticmethod
    def credenciais_acesso(participante):
        conteudo = []
        url_area_do_participante = f'{settings.SITE_URL}/eventos/autenticar_participante/{participante.evento.pk}/'
        conteudo.append('<h1>Credenciais de Acesso à Área do Participante</h1>')
        conteudo.append(f'<h2>{participante.evento.nome}</h2>')
        conteudo.append(f'<p>Caro(a) {participante.nome},</p>')
        conteudo.append('<p>Estamos enviando suas credenciais de acesso à área do participante do evento.</p>')
        conteudo.append(
            f'<p>Para acessar a área privativa do participante, você deve acessar o endereço: <a href="{url_area_do_participante}">{url_area_do_participante}</a>, informar o seu <b>e-mail</b> e a seguinte chave de acesso: <b>{participante.chave_acesso}</b></p>'
        )
        conteudo.append('<p>Agradecemos a sua participação e desejamos sucesso no evento!</p>')

        send_mail(
            '[SUAP] Credenciais de Acesso à Área do Participante',
            ''.join(conteudo),
            settings.DEFAULT_FROM_EMAIL,
            [participante.email],
        )
