from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.safestring import mark_safe
from sentry_sdk import capture_exception

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa
from catalogo_provedor_servico.providers.base import Etapa, GovBr_User_Info, Mask
from catalogo_provedor_servico.utils import Notificar
from comum.models import Configuracao
from comum.utils import get_setor
from djtools.utils import httprr
from documento_eletronico.models import DocumentoDigitalizado, TipoDocumento
from edu.models import Aluno, RegistroEmissaoDiploma
from edu.models.cadastros_gerais import SituacaoMatricula
from processo_eletronico.forms import FinalizarRequerimentoForm
from processo_eletronico.models import Processo, TipoProcesso, Tramite
from processo_eletronico.views import montar_requerimento_pdf_as_html

from .base import AbstractServiceProvider


class EmissaoSegundaViaDiplomaServiceProvider(AbstractServiceProvider):
    @staticmethod
    def choices_alunos(filters):
        alunos = Aluno.objects.filter(**filters)
        if not Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'desabilitar_execucao_segunda_via_diploma'):
            alunos = alunos.filter(registroemissaodiploma__isnull=False)
        else:
            alunos = Aluno.locals.filter(
                situacao__id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO]
            )
            alunos = alunos | Aluno.locals.filter(integralizou_ensino_medio=True)
            alunos = alunos.filter(matriz__isnull=False) | alunos.filter(codigo_academico__isnull=False)
            alunos = alunos.filter(**filters).distinct()
        choices = []
        for obj in alunos:
            choices.append((obj.id, f'{obj.matricula} - {obj.curso_campus.descricao}'))
        return dict(choices)

    def get_id_servico_portal_govbr(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_segunda_via_diploma') or 0)

    def _do_avaliacao_disponibilidade_especifica(self, cpf, servico, avaliacao):
        if Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'desabilitar_execucao_segunda_via_diploma'):
            qs = Aluno.locals.filter(
                situacao__id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO]
            )
            qs = qs | Aluno.locals.filter(integralizou_ensino_medio=True)
            qs = qs.filter(matriz__isnull=False) | qs.filter(codigo_academico__isnull=False)
            qs = qs.filter(pessoa_fisica__cpf=cpf).distinct()
            avaliacao.add_criterio(
                qs.exists(), f'Existem alunos concluídos para o CPF "{cpf}".', f'O aluno com o CPF "{cpf}" não existe ou ainda não concluíu o curso.'
            )
            return
        qs = RegistroEmissaoDiploma.objects.filter(aluno__pessoa_fisica__cpf=cpf)
        avaliacao.add_criterio(
            qs.exists(), f'Existem diplomas emitidos para o aluno com o CPF "{cpf}".', f'O aluno com o CPF "{cpf}" nunca emitiu um diploma.'
        )
        return

    def _get_etapa_1(self, cpf):
        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        if etapa_1:
            return etapa_1

        etapa_1 = Etapa(numero=1, total_etapas=self.get_numero_total_etapas(), nome='Etapa 1')
        etapa_1.formulario.add_string(
            label='Nome', name='nome', value=None, balcaodigital_user_info=GovBr_User_Info.NOME, required=True, read_only=True, max_length=200
        ).add_string(
            label='CPF', name='cpf', value=None, balcaodigital_user_info=GovBr_User_Info.CPF, mask=Mask.CPF, required=True, read_only=True
        ).add_string(
            label='E-mail', name='email', value=None, balcaodigital_user_info=GovBr_User_Info.EMAIL, required=True, read_only=True, max_length=200
        ).add_string(
            label='Telefone', name='telefone', value=None, balcaodigital_user_info=GovBr_User_Info.FONE, required=True, read_only=True, max_length=200
        )
        etapa_1.fieldsets.add(name='Dados Pessoais', fields=('nome', 'cpf', 'email', 'telefone'))

        etapa_1.formulario.add_choices(label='Matrícula', name='alunos', value=None, choices=self.choices_alunos, filters={'pessoa_fisica__cpf': cpf})
        etapa_1.fieldsets.add(name='Matrícula', fields=('alunos',))
        return etapa_1

    def executar_solicitacao(self, request, solicitacao):
        title = 'Solicitação de Emissão de Segunda via de Diploma'

        dados_email = self.get_dados_email(solicitacao=solicitacao)
        url_avaliacao = None
        if solicitacao.get_registroavaliacao_govbr():
            url_avaliacao = solicitacao.get_registroavaliacao_govbr().url_avaliacao
        if Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'desabilitar_execucao_segunda_via_diploma'):
            solicitacao.status = Solicitacao.STATUS_ATENDIDO
            solicitacao.status_detalhamento = f'Solicitação #{solicitacao.id} finalizada com sucesso.'
            solicitacao.save()
            mensagem_principal = f"""
                A sua solicitação #{solicitacao.id} foi finalizada. Caso necessário, entre em contato com a secretaria acadêmica do seu campus.
            """
            Notificar.notifica_conclusao_servico_atendido(
                solicitacao, dados_email=dados_email, mensagem=mensagem_principal, url_avaliacao=url_avaliacao
            )
            self.registrar_acompanhamento(solicitacao)

            # Enviando o e-mail com a notificação de serviço atendido com sucesso.
            self.obter_formulario_avaliacao(solicitacao)
            self.registrar_conclusao(solicitacao)
            return httprr('/admin/catalogo_provedor_servico/solicitacao/', 'A solicitação foi processada com sucesso.')

        form = FinalizarRequerimentoForm(request.POST or None, request=request, sugestao_primeiro_tramite=None)

        if form.is_valid():
            solicitacao_etapa = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1)
            dados = Etapa.load_from_json(solicitacao_etapa.get_dados_as_json())
            aluno = Aluno.objects.filter(pk=int(dados.formulario.get_value('alunos'))).first()

            with transaction.atomic():
                try:
                    tipo_processo = TipoProcesso.objects.get(
                        pk=Configuracao.get_valor_por_chave('processo_eletronico', 'tipo_processo_solicitar_emissao_diploma')
                    )
                    tipo_documento_requerimento = TipoDocumento.objects.get(
                        pk=Configuracao.get_valor_por_chave('documento_eletronico', 'tipo_documento_requerimento')
                    )
                except Exception:
                    raise ValidationError(
                        'Impossível obter parâmetros de configuação do Sistema: tipo_processo_solicitar_emissao_diploma e/ou tipo_documento_requerimento.'
                        ' Entre em contato com os administradores do sistema.'
                    )
                assunto = 'Solicitação de segunda via de diploma'
                processo = Processo.criar(tipo_processo=tipo_processo, assunto=assunto, interessados=[aluno.get_vinculo()])

                solicitacao.add_dado_registro_execucao(model_object=processo, operation='CREATE')

                requerimento_pdf_as_html = montar_requerimento_pdf_as_html(
                    request=request,
                    requerente_nome=aluno.pessoa_fisica.nome,
                    requerente_telefone=aluno.telefone_principal,
                    requerente_email=aluno.email_pessoal,
                    requerimento_destinatario_setor=form.get_destino(),
                    requerimento_tipo_processo=tipo_processo,
                    requerimento_assunto=processo.assunto,
                    requerimento_descricao=processo.assunto,
                    requerimento_data_hora_emissao=datetime.now(),
                )
                documento_digitalizado_requerimento = DocumentoDigitalizado.criar(
                    file_content=requerimento_pdf_as_html.content,
                    file_name='requerimento_externo.html',
                    tipo_documento=tipo_documento_requerimento,
                    assunto=processo.assunto,
                    user=request.user,
                    papel=form.cleaned_data.get('papel'),
                    nivel_acesso=DocumentoDigitalizado.NIVEL_ACESSO_RESTRITO,
                )

                solicitacao.add_dado_registro_execucao(model_object=documento_digitalizado_requerimento, operation='CREATE')

                documento_digitalizado_processo = processo.adicionar_documento_digitalizado(documento_digitalizado_requerimento)

                solicitacao.add_dado_registro_execucao(model_object=documento_digitalizado_processo, operation='CREATE')

                tramite_novo = Tramite()
                tem_depacho_para_assinar = bool(form.cleaned_data.get('despacho'))
                tramite_novo.processo = processo
                tramite_novo.tramitar_processo(
                    remetente_setor=get_setor(request.user),
                    remetente_vinculo=request.user.get_vinculo(),
                    despacho_corpo=form.cleaned_data.get('despacho'),
                    destinatario_vinculo=None,
                    destinatario_setor=form.get_destino(),
                    assinar_tramite=tem_depacho_para_assinar,
                    papel=form.cleaned_data.get('papel'),
                )
                solicitacao.add_dado_registro_execucao(model_object=tramite_novo, operation='CREATE')

                solicitacao.status = Solicitacao.STATUS_ATENDIDO
                solicitacao.status_detalhamento = (
                    f'Processo {processo.numero_protocolo_fisico}, para solicitação de emissão de diploma, criado com sucesso.'
                )
                solicitacao.save()

                # Registra acomapanhamento e indica conclusão do serviço junto ao GOVBR
                self.registrar_acompanhamento(solicitacao)
                # self.registrar_conclusao(solicitacao) #Todo: A conslusão vai ser informada após obter url_avaliacao
                # Enviando o e-mail com a notificação de serviço atendido com sucesso.
                self.obter_formulario_avaliacao(solicitacao)

                mensagem_principal = f"""
                                    A sua solicitação gerou o processo eletrônico número: {processo.numero_protocolo_fisico},
                                    você pode acompanhar os trâmites do processo na Consulta Pública do
                                    <a href="{settings.SITE_URL}/processo_eletronico/consulta_publica/">SUAP</a>
                                    """
                Notificar.notifica_conclusao_servico_atendido(
                    solicitacao, dados_email=dados_email, mensagem=mensagem_principal, url_avaliacao=url_avaliacao
                )
                return httprr(
                    '/admin/catalogo_provedor_servico/solicitacao/',
                    mark_safe(
                        f'A solicitação foi atendida através da criação do processo de número <a href={processo.get_absolute_url()}>{processo.numero_protocolo_fisico}</a>.'
                    ),
                    tag='success',
                )

        return locals()

    def is_em_periodo_avaliacao(self, solicitacao, campus=None):
        return True

    def get_dados_email(self, solicitacao):
        dados_email = []

        try:
            solicitacao_etapa1 = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=1).first()
            if solicitacao_etapa1:
                etapa1 = Etapa.load_from_json(solicitacao_etapa1.get_dados_as_json())
                nome = etapa1.formulario.get_field('nome')
                dados_email.append(nome)
                cpf = etapa1.formulario.get_field('cpf')
                dados_email.append(cpf)
                telefone = etapa1.formulario.get_field('telefone')
                dados_email.append(telefone)
                email = etapa1.formulario.get_field('email')
                dados_email.append(email)
                matricula = etapa1.formulario.get_field('alunos')
                dados_email.append(matricula)
                # Obtém fields com erro da etapa 1 caso exista
                if etapa1.formulario.get_campos_by_status(status='ERROR'):
                    dados_email += etapa1.formulario.get_campos_by_status(status='ERROR')
            return dados_email
        except Exception as e:
            if settings.DEBUG:
                raise Exception(f'Detalhes: {e}')
            capture_exception(e)

        return None

    def _on_persist_solicitacao_etapa(self, etapa, solicitacao_etapa, is_create, is_update):
        if etapa.numero == 1:
            aluno = Aluno.objects.filter(pk=int(etapa.formulario.get_value('alunos'))).first()

            if aluno:
                solicitacao_etapa.solicitacao.nome = aluno.pessoa_fisica.nome
                solicitacao_etapa.solicitacao.uo = aluno.campus
                solicitacao_etapa.solicitacao.save()
