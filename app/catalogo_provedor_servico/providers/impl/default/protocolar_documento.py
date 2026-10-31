from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.html import mark_safe
from redis.exceptions import LockError
from sentry_sdk import capture_exception

from catalogo_provedor_servico.forms import PeticaoEletronicaForm
from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa, SolicitacaoEtapaArquivo
from catalogo_provedor_servico.providers.base import Etapa, GovBr_User_Info, Mask, ValidationException
from catalogo_provedor_servico.utils import Notificar
from comum.models import Configuracao, PrestadorServico
from comum.types import PessoaFisicaCadastro, PessoaTelefoneCadastro, PrestadorServicoCadastro
from comum.utils import get_setor
from djtools.utils import atomic, httprr
from documento_eletronico.models import Documento, DocumentoDigitalizado, HipoteseLegal, TipoDocumento
from edu.models import Cidade
from processo_eletronico.models import Processo, TipoProcesso, Tramite
from processo_eletronico.views import montar_requerimento_pdf_as_html
from rh.models import UnidadeOrganizacional

from .base import AbstractServiceProvider


class ProtocolarDocumentoServiceProvider(AbstractServiceProvider):
    def get_id_servico_portal_govbr(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_protocolar_documento') or 0)

    def _validate_dados_etapa(self, request, etapa, solicitacao):
        has_errors = []
        if etapa.numero == 1:
            nome = etapa.formulario.get_value('nome')
            if not nome:
                has_errors.append('Nome é um campo obrigatório. Por favor, inicie a requisição novamente.')
            cpf = etapa.formulario.get_value('cpf')
            if not cpf:
                has_errors.append('CPF é um campo obrigatório.')
            email = etapa.formulario.get_value('email')
            if not email:
                has_errors.append('Email é um campo obrigatório.')
        else:
            assunto = etapa.formulario.get_value('assunto')
            if not assunto:
                has_errors.append('Assunto é um campo obrigatório.')
            descricao = etapa.formulario.get_value('descricao')
            if not descricao:
                has_errors.append('Descrição é um campo obrigatório.')
            campus = etapa.formulario.get_value('campus')
            if not campus:
                has_errors.append('Campus é um campo obrigatório.')

            for i in range(1, 7):
                if etapa.formulario.get_value(f'anexo_{i}_file') and not etapa.formulario.get_value(f'anexo_{i}_descricao'):
                    has_errors.append(f'Descrição do anexo {i} é um campo obrigatório.')

        return has_errors

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
                etapa2 = None
                # Obtém fields com erro da etapa 1 caso exista
                if etapa1.formulario.get_campos_by_status(status='ERROR'):
                    dados_email += etapa1.formulario.get_campos_by_status(status='ERROR')
                solicitacao_etapa2 = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1)
                # Obtém fields com erro da etapa 2 caso exista
                if solicitacao_etapa2:
                    etapa2 = Etapa.load_from_json(solicitacao_etapa1.get_dados_as_json())
                if etapa2 and etapa2.formulario.get_campos_by_status(status='ERROR'):
                    dados_email += etapa1.formulario.get_campos_by_status(status='ERROR')
            return dados_email
        except Exception as e:
            if settings.DEBUG:
                raise Exception(f'Detalhes: {e}')
            capture_exception(e)

    def _on_persist_solicitacao(self, solicitacao, is_create, is_update):
        pass

    def _on_persist_solicitacao_etapa(self, etapa, solicitacao_etapa, is_create, is_update):
        if etapa.numero == 1:
            solicitacao_etapa.solicitacao.nome = etapa.formulario.get_value('nome')
            solicitacao_etapa.solicitacao.save()

        if etapa.numero == 2:
            campus_id = etapa.formulario.get_value('campus')
            solicitacao_etapa.solicitacao.uo = UnidadeOrganizacional.objects.get(pk=campus_id)
            solicitacao_etapa.solicitacao.save()

    def _on_before_finish_recebimento_solicitacao(self, request, solicitacao):
        etapa_1 = self._get_etapa_para_edicao(cpf=solicitacao.cpf, numero_etapa=1)
        if not etapa_1:
            raise ValidationException('Primeira etapa não encotrada, por favor inicie a solicitação novamente.')
        etapa_1.formulario.set_avaliacao(name='declaracao_ciencia', status='OK')
        SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_1, solicitacao=solicitacao)

    @staticmethod
    def choices_unidade_organizacional():
        campi = UnidadeOrganizacional.objects.uo().all()
        data = {}
        for campus in campi:
            data[campus.pk] = campus.nome.upper()
        return data

    @staticmethod
    def choices_cidade():
        return Cidade.objects.all()

    def _get_etapa_1(self, cpf):
        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        if etapa_1:
            return etapa_1

        instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')

        declaracao_ciencia = (
            f'<b style="font-size:1.5em">DECLARO QUE ESTOU CIENTE DE QUE ESTE SERVIÇO NÃO TEM POR OBJETIVO A REALIZAÇÃO '
            f'DE MATRÍCULA EM PROCESSO SELETIVO OFERTADO PELO {instituicao_sigla}.</b>'
        )

        etapa_1 = Etapa(numero=1, total_etapas=self.get_numero_total_etapas(), nome='Etapa 1')

        etapa_1.formulario.add_boolean(
            label='Confirmo', help_text=mark_safe(declaracao_ciencia), name='declaracao_ciencia', value=None, required=True
        )
        etapa_1.fieldsets.add(name='Declaração de Ciência', fields=('declaracao_ciencia',))

        etapa_1.formulario.add_string(
            label='Nome', name='nome', value=None, balcaodigital_user_info=GovBr_User_Info.NOME, required=True, read_only=True, max_length=200
        ).add_string(
            label='CPF', name='cpf', value=None, balcaodigital_user_info=GovBr_User_Info.CPF, mask=Mask.CPF, required=True, read_only=True
        ).add_string(
            label='E-mail',
            name='email',
            value=None,
            balcaodigital_user_info=GovBr_User_Info.EMAIL if not settings.DEBUG else None,
            required=True,
            read_only=False,
            max_length=200,
        ).add_string(
            label='Telefone',
            name='telefone',
            value=None,
            help_text='Formato: (XX) XXXXX-XXXX',
            balcaodigital_user_info=GovBr_User_Info.FONE if not settings.DEBUG else None,
            required=True,
            read_only=False,
            mask=Mask.TELEFONE,
            max_length=200,
        )
        etapa_1.fieldsets.add(
            name='Dados Pessoais',
            fields=(
                'nome',
                'cpf',
                'email',
                'telefone',
            ),
        )

        etapa_1.formulario.add_string(label='Cep', name='cep', value=None, required=False, max_length=9, mask=Mask.CEP).add_string(
            label='Logradouro', name='logradouro', value=None, required=True
        ).add_string(label='Número', name='numero', value=None, required=True).add_string(
            label='Complemento', name='complemento', value=None, required=False
        ).add_string(label='Bairro', name='bairro', value=None, required=True).add_choices(
            label='Cidade', name='cidade', value=None, choices=self.choices_cidade, required=True
        )
        etapa_1.fieldsets.add(
            name='Endereço',
            fields=(
                'cep',
                'logradouro',
                'numero',
                'complemento',
                'cidade',
                'bairro',
            ),
        )

        return etapa_1

    def _get_etapa_2(self, cpf):
        etapa_2 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=2)
        if etapa_2:
            return etapa_2

        etapa_2 = Etapa(numero=2, total_etapas=self.get_numero_total_etapas(), nome='Etapa 2')
        etapa_2.formulario.add_string(label='Assunto', name='assunto', value=None, required=True, max_length=100).add_string(
            label='Descrição', name='descricao', value=None, required=True, max_length=510, widget='textarea'
        ).add_choices(label='Campus', name='campus', value=None, choices=self.choices_unidade_organizacional, required=True)
        etapa_2.fieldsets.add(name='Dados do Requerimento', fields=('assunto', 'descricao', 'campus'))

        for i in range(1, 7):
            etapa_2.formulario.add_string(label='Descrição', name=f'anexo_{i}_descricao', value=None, required=False, max_length=100).add_file(
                label='Anexo', name=f'anexo_{i}_file', value=None, label_to_file=f'Anexo{i}', allowed_extensions=['pdf'], required=False
            )
            etapa_2.fieldsets.add(
                name=f'Anexo {i}',
                fields=(
                    f'anexo_{i}_descricao',
                    f'anexo_{i}_file',
                ),
            )

        return etapa_2

    def executar_solicitacao(self, request, solicitacao):
        """

        :param request: Dados do request
        :param solicitacao: Solicitacao de serviço digital que será executada, neste caso cria um proceso eletrônico
        :return: HttpResponse com informação sobre execução (Sucesso, Erro)
        """
        title = 'Solicitação de Protocolo Eletrônico'

        dados_email = self.get_dados_email(solicitacao=solicitacao)
        url_avaliacao = None
        if solicitacao.get_registroavaliacao_govbr():
            url_avaliacao = solicitacao.get_registroavaliacao_govbr().url_avaliacao
        if Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'desabilitar_execucao_protocolar_documento'):
            solicitacao.status = Solicitacao.STATUS_ATENDIDO
            solicitacao.status_detalhamento = f'Solicitação #{solicitacao.id} finalizada com sucesso.'
            solicitacao.save()
            mensagem_principal = f"""
                A sua solicitação #{solicitacao.id} foi finalizada. Caso necessário, entre em contato com o setor responsável pela sua solicitação.
            """
            Notificar.notifica_conclusao_servico_atendido(
                solicitacao, dados_email=dados_email, mensagem=mensagem_principal, url_avaliacao=url_avaliacao
            )
            self.registrar_acompanhamento(solicitacao)

            # Enviando o e-mail com a notificação de serviço atendido com sucesso.
            self.obter_formulario_avaliacao(solicitacao)
            self.registrar_conclusao(solicitacao)
            return httprr('/admin/catalogo_provedor_servico/solicitacao/', 'A solicitação foi processada com sucesso.')

        solicitacao_etapa_1 = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1)
        etapa_1 = Etapa.load_from_json(solicitacao_etapa_1.get_dados_as_json())

        solicitacao_etapa_2 = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=2)
        etapa_2 = Etapa.load_from_json(solicitacao_etapa_2.get_dados_as_json())

        campus_id = etapa_2.formulario.get_value('campus')
        anexos = []
        for i in range(1, 7):
            anexo_file = f'anexo_{i}_file'
            if bool(etapa_2.formulario.get_field(anexo_file)) and etapa_2.formulario.get_field(anexo_file).get('value_hash_sha512_link_id'):
                anexo_descricao = f'anexo_{i}_descricao'
                anexos.append({'name': anexo_descricao, 'descricao': etapa_2.formulario.get_value(anexo_descricao)})

        form = PeticaoEletronicaForm(request.POST or None, request=request, anexos=anexos, campus_id=campus_id)

        if form.is_valid():
            try:
                with atomic(f'protocolar_documento_lock:{solicitacao.pk}', timeout=60):
                    nome = etapa_1.formulario.get_value('nome')
                    cpf = etapa_1.formulario.get_value('cpf')
                    telefone = etapa_1.formulario.get_value('telefone')
                    email = etapa_1.formulario.get_value('email')
                    assunto = etapa_2.formulario.get_value('assunto')
                    descricao = etapa_2.formulario.get_value('descricao')

                    pessoa_fisica_dict: PessoaFisicaCadastro = {
                        'cpf': cpf,
                        'nome_registro': nome,
                        'email_secundario': email,
                        'email': email,
                    }
                    telefone_dict: PessoaTelefoneCadastro = {
                        'numero': telefone,
                    }
                    dados: PrestadorServicoCadastro = {
                        'pessoa_fisica': pessoa_fisica_dict,
                        'telefone': telefone_dict,
                        'ativo': True,
                        'usuario_externo': True,
                    }

                    retorno = PrestadorServico.update_or_create(dados)
                    pessoa_fisica = retorno['pessoa_fisica']
                    usuario_externo = retorno['prestador']
                    usuario_externo_created = retorno['prestador_created']
                    pessoa_telefone = retorno['telefone']
                    pessoa_telefone_created = retorno['telefone_created']

                    solicitacao.add_dado_registro_execucao(model_object=usuario_externo, operation='CREATE' if usuario_externo_created else 'UPDATE')
                    solicitacao.add_dado_registro_execucao(model_object=pessoa_telefone, operation='CREATE' if pessoa_telefone_created else 'UPDATE')

                    try:
                        tipo_processo = TipoProcesso.objects.get(
                            pk=Configuracao.get_valor_por_chave('processo_eletronico', 'tipo_processo_demanda_externa_do_cidadao')
                        )
                        tipo_documento_requerimento = TipoDocumento.objects.get(
                            pk=Configuracao.get_valor_por_chave('documento_eletronico', 'tipo_documento_requerimento')
                        )
                        hipotese_legal = HipoteseLegal.objects.get(
                            pk=Configuracao.get_valor_por_chave('processo_eletronico', 'hipotese_legal_documento_abertura_requerimento')
                        )
                    except Exception:
                        raise ValidationError(
                            'Impossível obter parâmetros de configuação do Sistema: tipo_processo_solicitar_emissao_diploma e/ou tipo_documento_requerimento.'
                            ' Entre em contato com os administradores do sistema.'
                        )

                    requerimento_pdf_as_html = montar_requerimento_pdf_as_html(
                        request=request,
                        requerente_nome=nome,
                        requerente_telefone=telefone,
                        requerente_email=email,
                        requerimento_destinatario_setor=form.get_destino(),
                        requerimento_tipo_processo=tipo_processo,
                        requerimento_assunto=assunto,
                        requerimento_descricao=descricao,
                        requerimento_data_hora_emissao=datetime.now(),
                    )

                    documento_digitalizado_requerimento = DocumentoDigitalizado.criar(
                        file_content=requerimento_pdf_as_html.content,
                        file_name='requerimento_externo.html',
                        tipo_documento=tipo_documento_requerimento,
                        assunto=assunto,
                        user=request.user,
                        papel=form.cleaned_data.get('papel'),
                        nivel_acesso=Documento.NIVEL_ACESSO_RESTRITO,
                    )

                    solicitacao.add_dado_registro_execucao(model_object=documento_digitalizado_requerimento, operation='CREATE')
                    #
                    processo = Processo.criar(
                        tipo_processo=tipo_processo, assunto=assunto, interessados=[usuario_externo.get_vinculo()], hipotese_legal=hipotese_legal
                    )

                    documento_digitalizado_processo = processo.adicionar_documento_digitalizado(documento_digitalizado_requerimento)
                    solicitacao.add_dado_registro_execucao(model_object=documento_digitalizado_processo, operation='CREATE')

                    for i in range(1, 7):
                        nome_atributo_json = f'anexo_{i}_file'
                        sea = SolicitacaoEtapaArquivo.objects.filter(
                            solicitacao_etapa__solicitacao=solicitacao, solicitacao_etapa__numero_etapa=2, nome_atributo_json=nome_atributo_json
                        )
                        if sea.exists():
                            sea = sea.first()
                            anexo_tipo = form.cleaned_data.get(f'anexo_{i}_descricao_tipo')
                            nivel_acesso = int(form.cleaned_data.get(f'anexo_{i}_descricao_nivel_acesso'))
                            anexo_descricao = etapa_2.formulario.get_value(f'anexo_{i}_descricao')
                            documento_digitalizado = DocumentoDigitalizado.criar(
                                file_content=sea.arquivo_unico.get_conteudo_as_bytes(),
                                file_name=sea.nome_original,
                                tipo_documento=anexo_tipo,
                                assunto=anexo_descricao,
                                user=request.user,
                                papel=form.cleaned_data.get('papel'),
                                nivel_acesso=nivel_acesso,
                            )

                            solicitacao.add_dado_registro_execucao(model_object=documento_digitalizado, operation='CREATE')

                            documento_digitalizado_processo = processo.adicionar_documento_digitalizado(documento_digitalizado)

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
                    solicitacao.status_detalhamento = f'Processo {processo.get_numero_unico_protocolo()} criado com sucesso.'
                    solicitacao.save()
                    # Adicionando link pro aprocesso no detalhamento sem executar o save da solicitacao.
                    # TODO: Ver uma melhor forma de exibir os dados gerados a partir dessa solicitação, pois esse campo
                    # "status_detalhamento" não foi projetado para exibir isso. Uma alternativa que acho interessante
                    # é exibir os links a partir do atributo "dados_registros_execucao", que contém todos os objetos
                    # criados e ou modificados a partir da solicitaççao.
                    Solicitacao.objects.filter(pk=solicitacao.pk).update(
                        status_detalhamento=f'Processo <a href="{processo.get_absolute_url()}">{processo.get_numero_unico_protocolo()}</a> criado com sucesso.'
                    )

                    # Registra acomapanhamento e indica conclusão do serviço junto ao GOVBR
                    self.registrar_acompanhamento(solicitacao)

                    # Enviando o e-mail com a notificação de serviço atendido com sucesso.
                    self.obter_formulario_avaliacao(solicitacao)

                    mensagem_principal = f"""
                                        A sua solicitação gerou o processo eletrônico número: {processo.get_numero_unico_protocolo()},
                                        você pode acompanhar os trâmites do processo na Consulta Pública do  SUAP através do link:
                                        {settings.SITE_URL}/processo_eletronico/consulta_publica/
                                        """
                    Notificar.notifica_conclusao_servico_atendido(
                        solicitacao, dados_email=dados_email, mensagem=mensagem_principal, url_avaliacao=url_avaliacao
                    )
                    self.registrar_conclusao(solicitacao)

                    return httprr(
                        '/admin/catalogo_provedor_servico/solicitacao/',
                        mark_safe(
                            f'A solicitação foi atendida através da criação do processo de número <a href={processo.get_absolute_url()}>{processo.get_numero_unico_protocolo()}</a>.'
                        ),
                        tag='success',
                    )
            except LockError:
                return httprr('/admin/catalogo_provedor_servico/solicitacao/', 'A solicitação já está sendo processada.', tag='error')
            except ValidationError as e:
                return httprr('/admin/catalogo_provedor_servico/solicitacao/', f'Erro de validação. {e}', tag='error')

        return locals()
