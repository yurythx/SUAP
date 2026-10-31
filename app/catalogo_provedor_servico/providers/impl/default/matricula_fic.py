import logging
from collections import OrderedDict
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.safestring import mark_safe
from sentry_sdk import capture_exception

from catalogo_provedor_servico.forms import SolicitacaoMatriculaForm
from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa, SolicitacaoEtapaArquivo
from catalogo_provedor_servico.providers.base import Etapa, Mask
from catalogo_provedor_servico.utils import Notificar
from comum.models import Ano, Configuracao, PovoIndigena, Raca
from djtools.utils import httprr
from edu.forms import EfetuarMatriculaForm
from edu.models import Aluno, Cartorio, Cidade, Deficiencia, Estado, MatrizCurso, NivelEnsino, OrgaoEmissorRg, Pais, TipoNEE
from edu.models.arquivos import AlunoArquivo
from processo_seletivo.models import CandidatoVaga

from .base import AbstractMatriculaServiceProvider

logger = logging.getLogger(__name__)


class MatriculaFicServiceProvider(AbstractMatriculaServiceProvider):
    @staticmethod
    def choices_candidatos_vaga(filters):
        candidato_vagas = CandidatoVaga.matricula_online_disponibilidade(**filters)
        choices = []
        for obj in candidato_vagas:
            choices.append((obj['candidato_vaga_id'], obj['edital_descricao']))
        return dict(choices)

    @staticmethod
    def choices_sim_nao():
        return {'Sim': 'Sim', 'Não': 'Não'}

    @staticmethod
    def choices_sexo():
        return {'F': 'Feminino', 'M': 'Masculino'}

    @staticmethod
    def choices_nacionalidade():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_NACIONALIDADE_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_estado_civil():
        choices = OrderedDict()
        for k, v in Aluno.ESTADO_CIVIL_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_parentesco():
        choices = OrderedDict()
        for k, v in Aluno.PARENTESCO_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_estado():
        return Estado.objects.all()

    @staticmethod
    def choices_cidade():
        return Cidade.objects.all()

    @staticmethod
    def choices_zona_residencial():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_ZONA_RESIDENCIAL_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_deficiencias():
        return Deficiencia.objects.filter(ativo=True)

    @staticmethod
    def choices_outras_nees():
        return TipoNEE.objects.filter(ativo=True)

    @staticmethod
    def choices_poder_publico_responsavel_transporte():
        choices = OrderedDict()
        for k, v in Aluno.PODER_PUBLICO_RESPONSAVEL_TRANSPORTE_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_tipo_veiculo():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_VEICULO_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_tipo_sanguineo():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_SANGUINEO_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_pais():
        return Pais.objects.all().exclude(nome='Brasil')

    @staticmethod
    def choices_raca():
        return Raca.objects.all()

    @staticmethod
    def choices_povo_indigena():
        return PovoIndigena.objects.all()

    @staticmethod
    def choices_nivel_ensino():
        return NivelEnsino.objects.all()

    @staticmethod
    def choices_tipo_instituicao_origem():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_INSTITUICAO_ORIGEM_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_ano():
        ano_atual = datetime.now().year
        return Ano.objects.filter(ano__lte=ano_atual).order_by('-ano')

    @staticmethod
    def choices_orgao_emissao_rg():
        return OrgaoEmissorRg.objects.all()

    @staticmethod
    def choices_tipo_certidao():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_CERTIDAO_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_cartorio():
        return Cartorio.objects.all()

    def get_id_servico_portal_govbr(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_fic') or 0)

    def get_numero_total_etapas(self):
        return 8

    # def _on_persist_solicitacao(self, solicitacao, is_create, is_update):
    #     campus_zl_id = int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'id_campus_ead') or 0)
    #     if is_create:
    #         solicitacao.uo = UnidadeOrganizacional.objects.get(pk=campus_zl_id)
    #         solicitacao.save()

    def _on_persist_solicitacao_etapa(self, etapa, solicitacao_etapa, is_create, is_update):
        if etapa.numero == 2:
            solicitacao = solicitacao_etapa.solicitacao
            candidato_vaga = self.get_candidato_vaga(solicitacao)
            solicitacao.uo = candidato_vaga.candidato.curso_campus.diretoria.setor.uo
            solicitacao.nome = etapa.formulario.get_value('nome')
            solicitacao.save()

    def _on_before_finish_recebimento_solicitacao(self, request, solicitacao):
        etapa_1 = self._get_etapa_para_edicao(cpf=solicitacao.cpf, numero_etapa=1)
        etapa_1.formulario.set_avaliacao(name='candidato_vaga', status='OK')
        SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_1, solicitacao=solicitacao)

        etapa_7 = self._get_etapa_para_edicao(cpf=solicitacao.cpf, numero_etapa=7)
        if etapa_7:
            etapa_7.formulario.set_avaliacao(name='declaracao_legais', status='OK')
            SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_7, solicitacao=solicitacao)

        etapa_8 = self._get_etapa_para_edicao(cpf=solicitacao.cpf, numero_etapa=8)
        if etapa_8:
            etapa_8.formulario.set_avaliacao(name='declaracao_etnia', status='OK')
            etapa_8.formulario.set_avaliacao(name='declaracao_didatica', status='OK')
            etapa_8.formulario.set_avaliacao(name='declaracao_legais', status='OK')
            etapa_8.formulario.set_avaliacao(name='declaracao_veracidade', status='OK')
            etapa_8.formulario.set_avaliacao(name='declaracao_conclusao', status='OK')
            SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_8, solicitacao=solicitacao)

    def executar_solicitacao(self, request, solicitacao):
        def format_data(valor):
            if valor:
                data = str(valor).split('-')

                ano = None
                mes = None
                dia = None

                if len(data[0]) == 4:
                    ano = int(data[0])
                    mes = data[1]
                    dia = data[2]
                elif len(data[0]) == 2:
                    ano = int(data[2])
                    mes = data[1]
                    dia = data[0]

                if ano is not None:
                    if mes.startswith('0'):
                        mes = int(mes[1:])
                    else:
                        mes = int(mes)

                    if dia.startswith('0'):
                        dia = int(dia[1:])
                    else:
                        dia = int(dia)

                    return datetime(ano, mes, dia).date()
            return None

        title = 'Executar Solicitação'
        etapa_1_dados = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1).get_dados_as_json()

        candidato_vaga = None

        for dado in etapa_1_dados['formulario']:
            if dado['name'] == 'candidato_vaga':
                candidato_vaga = dado['value']
                break

        if candidato_vaga is None:
            raise Exception('Erro ao processar requisição')

        candidato_vaga = CandidatoVaga.objects.filter(pk=candidato_vaga).first()

        if candidato_vaga is None:
            raise Exception('Erro ao processar requisição, candidato inexistente')

        qs_matriz_curso = MatrizCurso.objects.filter(curso_campus=candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus).order_by('-id')
        ano_letivo = candidato_vaga.candidato.edital.ano_id
        periodo_letivo = candidato_vaga.candidato.edital.semestre
        turno = candidato_vaga.candidato.turno and candidato_vaga.candidato.turno_id or None
        forma_ingresso = candidato_vaga.oferta_vaga.lista.forma_ingresso and candidato_vaga.oferta_vaga.lista.forma_ingresso_id or None
        matriz_curso = qs_matriz_curso.exists() and qs_matriz_curso[0].pk or None
        nome = ''
        for etapa in solicitacao.solicitacaoetapa_set.all():
            for field in etapa.get_dados_as_json()['formulario']:
                if field['name'] == 'nome':
                    nome = field['value']
                    break

        initial = {
            'cpf': candidato_vaga.candidato.cpf,
            'nome': nome or candidato_vaga.candidato.nome,
            'ano_letivo': ano_letivo,
            'periodo_letivo': periodo_letivo,
            'turno': turno,
            'forma_ingresso': forma_ingresso,
            'matriz_curso': matriz_curso,
        }

        form = SolicitacaoMatriculaForm(request.POST or None, candidato_vaga=candidato_vaga, initial=initial)

        if form.is_valid():
            form_matricula = EfetuarMatriculaForm(request=request, candidato_vaga=candidato_vaga)

            data_post = {}

            for field, value in form.cleaned_data.items():
                if hasattr(value, 'pk'):
                    data_post[field] = value.pk
                else:
                    data_post[field] = value

            for etapa in solicitacao.solicitacaoetapa_set.all():
                for field in etapa.get_dados_as_json()['formulario']:
                    if field['name'] == 'cpf':
                        continue

                    if field['name'] in form_matricula.base_fields:
                        value = field['value']
                        if field['name'] in ['pai_falecido', 'mae_falecida', 'aluno_especial']:
                            value = False

                        if field['type'] == 'date':
                            value = format_data(value)

                        if field['name'] in ['deficiencias', 'outras_nees'] and value:
                            value = [value]

                        data_post[field['name']] = value

            form_matricula = EfetuarMatriculaForm(request, candidato_vaga, data=data_post)
            if form_matricula.is_valid():
                try:
                    with transaction.atomic():
                        aluno = form_matricula.processar()
                        solicitacao.add_dado_registro_execucao(model_object=aluno, operation='CREATE')

                        try:
                            logger.info('Obtendo foto 3x4 do aluno.')
                            solicitacao_etapa_arquivo_foto = SolicitacaoEtapaArquivo.objects.filter(
                                solicitacao_etapa__solicitacao=solicitacao, nome_atributo_json='foto_3x4'
                            )
                            if solicitacao_etapa_arquivo_foto.exists():
                                logger.info('Salvando foto 3x4 no cadastro do aluno.')
                                solicitacao_etapa_arquivo_foto = solicitacao_etapa_arquivo_foto.first()
                                content_file = ContentFile(solicitacao_etapa_arquivo_foto.arquivo_unico.get_conteudo_as_bytes())
                                aluno.foto.save(solicitacao_etapa_arquivo_foto.nome_original, content_file, save=True)
                                logger.info('Foto 3x4 salva com sucesso.')
                        except Exception as e:
                            logger.warning(f'Erro ao tentar salvar foto 3x4 no cadastro do aluno. Detalhes: {e!s}')
                            capture_exception(e)

                        # TODO: Verificar com equipe se esse teste ainda é necessário
                        if aluno.pessoa_fisica.cpf != candidato_vaga.candidato.cpf:
                            raise ValidationError(
                                'A solicitação não poder ser marcado com "Atendida" pois o CPF do aluno diverge do CPF do solicitante.'
                            )

                        # Fazendo o registro de todos os documentos enviados pelo aluno, durante a matrícula, na sua "pasta de documentos".
                        solicitacao_etapa_arquivos = SolicitacaoEtapaArquivo.objects.filter(solicitacao_etapa__solicitacao=solicitacao)
                        if solicitacao_etapa_arquivos.exists():
                            for sea in solicitacao_etapa_arquivos:
                                aluno_etapa_arquivo = AlunoArquivo()

                                observacao = 'Documento fornecido pelo aluno durante matrícula online'
                                if len(observacao) > 255:
                                    observacao = f'{observacao[:250]} ...'
                                aluno_etapa_arquivo.observacao = observacao
                                aluno_etapa_arquivo.tipo_origem_cadastro = AlunoArquivo.TIPO_ORIGEM_CADASTRO_MATRICULA_ONLINE

                                aluno_etapa_arquivo.aluno = aluno
                                aluno_etapa_arquivo.arquivo_unico = sea.arquivo_unico
                                aluno_etapa_arquivo.nome_original = sea.nome_original
                                aluno_etapa_arquivo.nome_exibicao = sea.nome_exibicao
                                aluno_etapa_arquivo.descricao = sea.descricao
                                aluno_etapa_arquivo.tipo = AlunoArquivo.get_tipo_para_matricula_online(sea.descricao)
                                aluno_etapa_arquivo.data_hora_upload = sea.data_hora_upload

                                aluno_etapa_arquivo.data_validacao = aluno_etapa_arquivo.data_hora_upload
                                aluno_etapa_arquivo.prazo_validade = aluno_etapa_arquivo.prazo_validade or 6
                                aluno_etapa_arquivo.data_expiracao = aluno_etapa_arquivo.data_validacao.date() + relativedelta(
                                    years=aluno_etapa_arquivo.prazo_validade
                                )

                                aluno_etapa_arquivo.save()
                                solicitacao.add_dado_registro_execucao(model_object=aluno_etapa_arquivo, operation='CREATE')

                        # Registra solicitação com ATENDIDA.
                        solicitacao.status = Solicitacao.STATUS_ATENDIDO
                        # Esse status será enviado pra o aluno.
                        solicitacao.status_detalhamento = 'Matrícula realizada com sucesso.'

                        solicitacao.add_dado_registro_execucao(model_object=candidato_vaga, operation='UPDATE')

                        solicitacao.save()

                        # Registrando a matricula do aluno junto ao módulo de processo seletivo
                        candidato_vaga.registrar_matricula()

                        # Adicionando link pra matrícula detalhamento, sem executar o save da solicitacao.
                        # Isso aparecerá só para o avaliador, na tela de avaliação.
                        Solicitacao.objects.filter(pk=solicitacao.pk).update(
                            status_detalhamento=f'Matrícula <a href="/edu/aluno/{aluno.matricula}">{aluno.matricula}</a> realizada com sucesso.'
                        )

                        # Registra acompanhamento e indica conclusão do serviço junto ao GOVBR
                        self.registrar_acompanhamento(solicitacao)

                        dados_email = self.get_dados_email(solicitacao=solicitacao)

                        # Envia e-mail para aluno com comprovante de matrícula
                        # Este e-mail não esta sendo enviado pelo Notifica Gov.BR pois a plataforma ainda não tem
                        # a funcionalidade de envio de anexo habilitada
                        Notificar.envia_comprovante_matricula(request, dados_email=dados_email, aluno=aluno)

                        # Tenta obter formulário de avaliação do serviço
                        self.obter_formulario_avaliacao(solicitacao)

                        url_avaliacao = None
                        if solicitacao.get_registroavaliacao_govbr():
                            url_avaliacao = solicitacao.get_registroavaliacao_govbr().url_avaliacao

                        Notificar.notifica_conclusao_servico_atendido(solicitacao, dados_email=dados_email, url_avaliacao=url_avaliacao)
                        self.registrar_conclusao(solicitacao)

                        return httprr(
                            '/admin/catalogo_provedor_servico/solicitacao/',
                            mark_safe(
                                f'A solicitação foi atendida com sucesso e gerou a matrícula <a href={aluno.get_absolute_url()}>{aluno.matricula}</a> para o aluno {aluno.pessoa_fisica.nome}.'
                            ),
                            tag='success',
                        )

                except IntegrityError as e:
                    if settings.DEBUG:
                        raise e
                    # TODO: Gugu, esse pass é ficar assim mesmo?
            else:
                # if settings.DEBUG:
                #    print(form_matricula.errors)
                #    print(form_matricula.non_field_errors())
                for key, value in form_matricula.errors.items():
                    form.errors[key] = value
                form.errors[NON_FIELD_ERRORS] = form_matricula.non_field_errors()

        return locals()

    def _do_avaliacao_disponibilidade_especifica(self, cpf, servico, avaliacao):
        """
        Código utilizado para teste do método
        from catalogo_provedor_servico.providers.base import *
        from catalogo_provedor_servico.providers.factory import *
        from catalogo_provedor_servico.models import *

        cpfs = (('108.795.654-46', 'Caso Hugo'),('115.902.124-44', 'Incompleto'),('011.692.834-46', 'Em Analise'),('701.221.354-07', 'Aguardando Correção'),('107.354.624-10', 'Dados Corrigidos'),('708.338.824-57', 'Atendido'),('706.511.634-47', 'Não Atendido'),('070.003.044-13', 'Ausente'), ('039.749.154-94', 'De Hugo'))
        for cpf, tipo in cpfs:
            print('-' * 60)
            print(f'CPF = {cpf}; Tipo = {tipo}')
            servicos = service_provider_factory().get_servicos_disponiveis(cpf)
            print('*' * 60)

        :param cpf:
        :return:
        """
        # Condições para tornar disponível a avaliação
        # 1 - O cidadão está aprovado em um edital que está em peróiodo de matrícula
        # 2 - O cidadão iniciou uma solicitação que está pendente de correção de dados e o edital está dentro do limite de correção

        # Lista contendo todos os candidatos vaga de um cidadão que está em período de matrícula, dentro do limite de correção ou vazio
        int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'id_campus_ead') or 0)  # FIXME: Precisa excluir do campus ead?
        candidato_vagas = CandidatoVaga.matricula_online_disponibilidade(cpf=cpf, niveis_ensino=[NivelEnsino.FUNDAMENTAL])

        em_periodo_matricula = False
        em_periodo_avaliacao = False

        for candidato_vaga in candidato_vagas:
            solicitacao = Solicitacao.objects.filter(cpf=cpf, servico=servico)

            # A variável "solicitacoes_a_serem_avaliadas_ids" evita com que solicitações de processos seletivos anteriores
            # acabem impedido o cidadão de fazer solicitar nova matrícula. Ex: No processo seletivo A o candidato perdeu
            # o prazo para a correção de dados e seu pedido foi EXPIRADO. Em um novo processo seletivo, B, essa solicitação
            # anterior, com um "candidato_vaga" anterior, não deve ser levado em conta.
            solicitacoes_anteriores_que_nao_devem_ser_levadas_em_conta_ids = []
            for s in solicitacao:
                solicitacao_etapa_1 = SolicitacaoEtapa.objects.filter(solicitacao=s, numero_etapa=1)
                if solicitacao_etapa_1:
                    solicitacao_etapa_1 = solicitacao_etapa_1.first()
                    etapa_1 = Etapa.load_from_json(solicitacao_etapa_1.get_dados_as_json())
                    candidato_vaga_id = int(etapa_1.formulario.get_value('candidato_vaga'))
                    if candidato_vaga_id != candidato_vaga['candidato_vaga_id']:
                        solicitacoes_anteriores_que_nao_devem_ser_levadas_em_conta_ids.append(s.id)
            if solicitacoes_anteriores_que_nao_devem_ser_levadas_em_conta_ids:
                solicitacao = solicitacao.exclude(id__in=solicitacoes_anteriores_que_nao_devem_ser_levadas_em_conta_ids)

            # Rotina anterior vigente até 13/07/2020, com o ajuste para passar a levar em conta a variável
            # "solicitacoes_anteriores_que_nao_devem_ser_levadas_em_conta_ids".
            # solicitacao = Solicitacao.objects.filter(cpf=cpf, servico=servico)
            if candidato_vaga['em_periodo_matricula']:
                em_periodo_matricula = True
                if solicitacao.exists():
                    em_periodo_matricula = solicitacao.first().status not in Solicitacao.STATUS_DEFINITIVOS
            else:
                if Solicitacao.objects.filter(cpf=cpf, servico=servico, status=Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS).exists():
                    em_periodo_avaliacao = True
                    if solicitacao.exists():
                        em_periodo_avaliacao = solicitacao.first().status not in Solicitacao.STATUS_DEFINITIVOS

        em_disponibilidade = em_periodo_matricula or em_periodo_avaliacao

        mensagem = ''
        if em_disponibilidade:
            if em_periodo_matricula:
                mensagem = 'Há editais em que o cidadão foi aprovado e o período de matrícula está aberto.'
            elif em_periodo_avaliacao:
                mensagem = 'Há editais em que o cidadão foi aprovado, o período de correção está vigente e sua solicitação em análise.'

        avaliacao.add_criterio(
            em_disponibilidade,
            mensagem,
            'Não há editais em que o cidadão foi aprovado, ou não estão em período de matrícula nem em período de avaliação.',
        )

    def _validate_dados_etapa(self, request, etapa, solicitacao):
        has_errors = super()._validate_dados_etapa(request=request, etapa=etapa, solicitacao=solicitacao)
        if etapa.numero == 2:
            mensagem_nee = 'Informe a deficiência ou outra NEE do aluno.'
            has_errors = [error for error in has_errors if mensagem_nee not in error]
        return has_errors

    def _get_next_etapa(self, cpf, etapa):
        if etapa.numero == 1:
            return self._get_etapa_2(cpf=cpf)
        if etapa.numero == 2:
            aluno_pne = etapa.formulario.get_value('aluno_pne') == 'Sim'
            if self._is_cota_renda_baixa(cpf):
                return self._get_etapa_3(cpf=cpf)
            if aluno_pne:
                return self._get_etapa_4(cpf=cpf)
            return self._get_etapa_5(cpf=cpf)
        if etapa.numero == 3:
            etapa_2 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=2)
            aluno_pne = etapa_2 and etapa_2.formulario.get_value('aluno_pne')
            # Compatibilidade com solicitações antigas em que `aluno_pne` estava na etapa 3.
            if not aluno_pne:
                aluno_pne = etapa.formulario.get_value('aluno_pne')
            if aluno_pne == 'Sim':
                return self._get_etapa_4(cpf=cpf)
            return self._get_etapa_5(cpf=cpf)
        if etapa.numero == 4:
            return self._get_etapa_5(cpf=cpf)
        if etapa.numero == 5:
            return self._get_etapa_6(cpf=cpf)
        if etapa.numero == 6:
            return self._get_etapa_7(cpf=cpf)
        if etapa.numero == 7:
            return self._get_etapa_8(cpf=cpf)

    def _get_etapa_1(self, cpf):
        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        if etapa_1:
            return etapa_1

        etapa_1 = Etapa(numero=1, total_etapas=self.get_numero_total_etapas(), nome='Etapa 1')
        etapa_1.formulario.add_choices(
            label='Edital / Vaga',
            name='candidato_vaga',
            value=None,
            choices=self.choices_candidatos_vaga,
            filters={'cpf': cpf, 'niveis_ensino': [NivelEnsino.FUNDAMENTAL]},
        )
        etapa_1.fieldsets.add(
            name='Seleção do Edital',
            fields=('candidato_vaga', 'modalidade_oferta', 'campus_oferta', 'turno_oferta', 'programa_convenio'),
        )
        return etapa_1

    def _get_etapa_2(self, cpf):
        etapa_2 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=2)

        if not etapa_2:
            etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
            candidato_vaga = CandidatoVaga.objects.get(pk=etapa_1.formulario.get_value('candidato_vaga'))
            sgc_dados_candidato = CandidatoVaga.matricula_online_dados_candidato(candidato_vaga_id=candidato_vaga.pk)
            sgc_dados_candidato = BeautifulSoup(sgc_dados_candidato, 'xml')

            dados_pessoais = sgc_dados_candidato.dados_pessoais
            lista = sgc_dados_candidato.inscricao.lista
            nome_edital = candidato_vaga.candidato.edital.descricao
            dados_oferta = self._get_dados_edital_oferta(candidato_vaga)

            estado_value = self.clear_value(dados_pessoais.endereco_uf.string)
            estado_value = Estado.ESTADOS.get(estado_value.upper(), '')

            cidade_value = ''
            value = self.clear_value(dados_pessoais.endereco_municipio.string)
            cidade = Cidade.objects.filter(nome=value.upper(), estado_id=estado_value).first()
            if cidade:
                cidade_value = cidade.pk

            data_nascimento = self.clear_date(dados_pessoais.nascimento_data.string)
            idade = self.get_idade(data_nascimento)
            responsavel_required = idade < 18

            etapa_2 = Etapa(numero=2, total_etapas=self.get_numero_total_etapas(), nome='Etapa 2')

            etapa_2.formulario.add_string(label='Edital', name='edital_nome', value=self.clear_value(nome_edital), read_only=True).add_string(
                label='Vaga', name='edital_vaga', value=candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus.descricao_historico, read_only=True
            ).add_string(label='Lista', name='edital_lista', value=self.clear_value(lista.nome.string), read_only=True).add_string(
                label='Programa/Convênio', name='programa_convenio', value=dados_oferta['programa'], read_only=True
            ).add_string(label='Campus', name='campus_oferta', value=dados_oferta['campus'], read_only=True).add_string(
                label='Turno de Oferta', name='turno_oferta', value=dados_oferta['turno'], read_only=True
            )
            etapa_2.fieldsets.add(
                name='Dados do Edital',
                fields=('edital_nome', 'edital_vaga', 'edital_lista', 'programa_convenio', 'campus_oferta', 'turno_oferta'),
            )

            etapa_2.formulario.add_string(
                label='CPF', name='cpf', value=self.clear_value(dados_pessoais.cpf.string), read_only=True, mask=Mask.CPF, required=True
            ).add_choices(label='Nacionalidade', name='nacionalidade', value='', choices=self.choices_nacionalidade, required=True).add_string(
                label='Nº do Passaporte (obrigatório para estrangeiros)', name='passaporte', value='', required=False, max_length=50
            ).add_choices(label='E portador de NEE?', name='aluno_pne', value='', choices=self.choices_sim_nao, required=True)
            etapa_2.fieldsets.add(name='Identificação', fields=('cpf', 'nacionalidade', 'passaporte', 'aluno_pne'))

            etapa_2.formulario.add_string(
                label='Nome', name='nome', value=self.clear_value(dados_pessoais.nome.string), required=True, max_length=200
            ).add_choices(
                label='Sexo', name='sexo', value=self.clear_value(dados_pessoais.sexo.string), choices=self.choices_sexo, required=True
            ).add_date(label='Data de Nascimento', name='data_nascimento', value=data_nascimento, mask=Mask.DATE, required=True).add_choices(
                label='Estado Civil',
                name='estado_civil',
                value=self.clear_value(dados_pessoais.estado_civil.string),
                choices=self.choices_estado_civil,
                required=True,
            ).add_file(
                label='Foto 3x4 recente',
                name='foto_3x4',
                value=None,
                label_to_file='Foto 3x4',
                allowed_extensions=settings.DEFAULT_UPLOAD_ALLOWED_IMAGE_EXTENSIONS,
                required=True,
                help_text='Formatos JPG/PNG. Tamanho recomendado ate 5MB.',
            )
            etapa_2.fieldsets.add(name='Dados Pessoais', fields=('nome', 'sexo', 'data_nascimento', 'estado_civil', 'foto_3x4'))

            etapa_2.formulario.add_string(
                label='Cep', name='cep', value=self.clear_value(dados_pessoais.endereco_cep.string), required=False, max_length=9, mask=Mask.CEP
            ).add_string(
                label='Logradouro', name='logradouro', value=self.clear_value(dados_pessoais.endereco_logradouro.string), required=True
            ).add_string(label='Número', name='numero', value=self.clear_value(dados_pessoais.endereco_numero.string), required=True).add_string(
                label='Complemento', name='complemento', value=self.clear_value(dados_pessoais.endereco_complemento.string), required=False
            ).add_string(label='Bairro', name='bairro', value=self.clear_value(dados_pessoais.endereco_bairro.string), required=True).add_choices(
                label='Estado', name='estado', value=estado_value, choices=self.choices_estado, required=False
            ).add_choices(label='Cidade', name='cidade', value=cidade_value, choices=self.choices_cidade, required=True).add_choices(
                label='Zona Residencial',
                name='tipo_zona_residencial',
                value=self.clear_value(dados_pessoais.endereco_zona_residencial.string),
                choices=self.choices_zona_residencial,
                required=True,
            )
            etapa_2.fieldsets.add(
                name='Endereço', fields=('cep', 'logradouro', 'numero', 'complemento', 'estado', 'cidade', 'bairro', 'tipo_zona_residencial')
            )

            etapa_2.formulario.add_string(
                label='Nome do Pai', name='nome_pai', value=self.clear_value(dados_pessoais.pai_nome.string), required=False
            ).add_choices(
                label='Estado Civil do Pai', name='estado_civil_pai', value='', choices=self.choices_estado_civil, required=False
            ).add_boolean(label='Pai Falecido?', name='pai_falecido', value=False, required=False)
            etapa_2.fieldsets.add(name='Filiação - Pai', fields=('nome_pai', 'pai_falecido', 'estado_civil_pai'))

            etapa_2.formulario.add_string(
                label='Nome da Mãe', name='nome_mae', value=self.clear_value(dados_pessoais.mae_nome.string), required=True
            ).add_choices(
                label='Estado Civil da Mãe', name='estado_civil_mae', value='', choices=self.choices_estado_civil, required=False
            ).add_boolean(label='Mãe Falecida?', name='mae_falecida', value=False, required=False)
            etapa_2.fieldsets.add(name='Filiação - Mãe', fields=('nome_mae', 'mae_falecida', 'estado_civil_mae'))

            etapa_2.formulario.add_string(
                label='Telefone Principal',
                name='telefone_principal',
                value=self.clear_value(dados_pessoais.telefone_residencial.string),
                required=False,
                help_text='Formato: (XX) XXXXX-XXXX',
                mask=Mask.TELEFONE,
            ).add_string(
                label='Telefone Secundário',
                name='telefone_secundario',
                value=self.clear_value(dados_pessoais.telefone_celular.string),
                required=False,
                help_text='Formato: (XX) XXXXX-XXXX',
                mask=Mask.TELEFONE,
            ).add_string(
                label='E-mail Pessoal',
                name='email_pessoal',
                value='' if settings.DEBUG else self.clear_value(dados_pessoais.email.string),
                required=True,
            )
            etapa_2.fieldsets.add(name='Contatos', fields=('telefone_principal', 'telefone_secundario', 'email_pessoal'))

            etapa_2.formulario.add_string(label='Nome do Responsável', name='responsavel', value='', required=responsavel_required).add_string(
                label='CPF do Responsável', name='cpf_responsavel', value='', mask=Mask.CPF, required=responsavel_required
            ).add_choices(
                label='Parentesco do Responsável',
                name='parentesco_responsavel',
                choices=self.choices_parentesco,
                value='',
                required=responsavel_required,
            ).add_string(
                label='Telefone do Responsável', name='telefone_adicional_1', value='', required=responsavel_required, mask=Mask.TELEFONE
            ).add_string(label='E-mail do Responsável', name='email_responsavel', value='', required=responsavel_required).add_file(
                label='Termo de Responsabilidade',
                name='termo_responsabilidade_menor',
                value=None,
                label_to_file='Termo de Responsabilidade',
                required=responsavel_required,
            ).add_file(
                label='Identidade do Responsável',
                name='documento_responsavel',
                value=None,
                label_to_file='Identidade do Responsável',
                required=responsavel_required,
            )
            etapa_2.fieldsets.add(
                name='Responsável Legal',
                fields=(
                    'responsavel',
                    'cpf_responsavel',
                    'parentesco_responsavel',
                    'telefone_adicional_1',
                    'email_responsavel',
                    'termo_responsabilidade_menor',
                    'documento_responsavel',
                ),
            )

        return etapa_2

    def _get_etapa_3(self, cpf):
        etapa_3 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=3)

        if not etapa_3:
            etapa_3 = Etapa(numero=3, total_etapas=self.get_numero_total_etapas(), nome='Etapa 3')
            now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

            etapa_3.formulario.add_string(
                label='CadUnico (API)', name='cadunico_status_api', value='Nao integrado', read_only=True, required=False
            ).add_string(label='Data/Hora da Consulta', name='cadunico_data_consulta', value=now_str, read_only=True, required=False).add_file(
                label='Comprovante CadUnico',
                name='comprovante_cadunico',
                value=None,
                label_to_file='Comprovante CadUnico',
                required=False,
                help_text='Se atualizado ha menos de 18 meses, pode dispensar os demais comprovantes de renda.',
            )
            etapa_3.fieldsets.add(name='CadUnico', fields=('cadunico_status_api', 'cadunico_data_consulta', 'comprovante_cadunico'))

            etapa_3.formulario.add_integer(
                label='Numero de Membros da Familia', name='renda_numero_membros_familia', value='', required=True, min_value=1
            )
            etapa_3.fieldsets.add(name='Composição Familiar', fields=('renda_numero_membros_familia',))

            for i in range(1, 6):
                etapa_3.formulario.add_string(label=f'Membro {i} - Nome', name=f'renda_membro_{i}_nome', value='', required=False).add_choices(
                    label=f'Membro {i} - Parentesco', name=f'renda_membro_{i}_parentesco', choices=self.choices_parentesco, value='', required=False
                ).add_choices(
                    label=f'Membro {i} - Menor de Idade?',
                    name=f'renda_membro_{i}_menor_idade',
                    choices=self.choices_sim_nao,
                    value='',
                    required=False,
                )
                etapa_3.fieldsets.add(
                    name=f'Membro Familiar {i}',
                    fields=(f'renda_membro_{i}_nome', f'renda_membro_{i}_parentesco', f'renda_membro_{i}_menor_idade'),
                )

            etapa_3.formulario.add_file(
                label='Comprovantes - Assalariado', name='renda_assalariado_docs', value=None, label_to_file='Assalariado', required=False
            ).add_file(label='Comprovantes - Atividade Rural', name='renda_rural_docs', value=None, label_to_file='Rural', required=False).add_file(
                label='Comprovantes - Aposentado/Pensionista', name='renda_aposentado_docs', value=None, label_to_file='Aposentado', required=False
            ).add_file(label='Comprovantes - Autonomo', name='renda_autonomo_docs', value=None, label_to_file='Autonomo', required=False).add_file(
                label='Comprovantes - Aluguel/Arrendamento', name='renda_aluguel_docs', value=None, label_to_file='Aluguel', required=False
            )
            etapa_3.fieldsets.add(
                name='Comprovantes de Renda',
                fields=('renda_assalariado_docs', 'renda_rural_docs', 'renda_aposentado_docs', 'renda_autonomo_docs', 'renda_aluguel_docs'),
            )

        return etapa_3

    def _get_etapa_4(self, cpf):
        etapa_4 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=4)
        if etapa_4:
            return etapa_4

        etapa_4 = Etapa(numero=4, total_etapas=self.get_numero_total_etapas(), nome='Etapa 4')
        etapa_4.formulario.add_choices(
            label='Deficiência', name='deficiencias', value=None, choices=self.choices_deficiencias, required=True
        ).add_choices(label='Outras NEEs', name='outras_nees', value=None, choices=self.choices_outras_nees, required=False)
        etapa_4.fieldsets.add(name='Tipo de Deficiência', fields=('deficiencias', 'outras_nees'))

        etapa_4.formulario.add_file(
            label='Laudo Médico com CID (CRM e RQE)', name='copia_laudo_medico', value=None, label_to_file='Laudo Médico', required=True
        ).add_file(label='Exames Complementares', name='exames_complementares_nee', value=None, label_to_file='Exames Complementares', required=False)
        etapa_4.fieldsets.add(name='Documentação PcD / NEE', fields=('copia_laudo_medico', 'exames_complementares_nee'))
        return etapa_4

    def _get_etapa_5(self, cpf):
        etapa_5 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=5)

        if not etapa_5:
            etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
            etapa_2 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=2)
            candidato_vaga = etapa_1.formulario.get_value('candidato_vaga')
            sgc_dados_candidato = CandidatoVaga.matricula_online_dados_candidato(candidato_vaga_id=candidato_vaga)
            sgc_dados_candidato = BeautifulSoup(sgc_dados_candidato, 'xml')
            dados_pessoais = sgc_dados_candidato.dados_pessoais

            pais_origem_value = Pais.objects.filter(nome__iexact=self.clear_value(dados_pessoais.nascimento_pais.string))
            if pais_origem_value.exists():
                pais_origem_value = pais_origem_value.first().pk
            else:
                pais_origem_value = ''

            estado_naturalidade_value = Estado.ESTADOS.get(self.clear_value(dados_pessoais.nascimento_uf.string), '')
            naturalidade_value = ''
            if estado_naturalidade_value:
                value = self.clear_value(dados_pessoais.nascimento_municipio.string)
                cidade = Cidade.objects.filter(nome=value.upper(), estado_id=estado_naturalidade_value).first()
                if cidade:
                    naturalidade_value = cidade.pk

            etapa_5 = Etapa(numero=5, total_etapas=self.get_numero_total_etapas(), nome='Etapa 5')

            etapa_5.formulario.add_choices(
                label='Tipo Sanguíneo', name='tipo_sanguineo', value='', choices=self.choices_tipo_sanguineo, required=False
            ).add_file(label='Carteira de Vacinação', name='carteira_vacinacao', value=None, label_to_file='Carteira de Vacinação', required=False)
            etapa_5.fieldsets.add(name='Saúde', fields=('tipo_sanguineo', 'carteira_vacinacao'))

            etapa_5.formulario.add_choices(
                label='Utiliza Transporte Escolar Público',
                name='utiliza_transporte_escolar_publico',
                value='',
                choices=self.choices_sim_nao,
                required=False,
            ).add_choices(
                label='Poder Público Responsável pelo Transporte Escolar',
                name='poder_publico_responsavel_transporte',
                value='',
                choices=self.choices_poder_publico_responsavel_transporte,
                required=False,
            ).add_choices(
                label='Tipo de Veículo Utilizado no Transporte Escolar',
                name='tipo_veiculo',
                value='',
                choices=self.choices_tipo_veiculo,
                required=False,
            )
            etapa_5.fieldsets.add(
                name='Transporte Escolar Utilizado',
                fields=('utiliza_transporte_escolar_publico', 'poder_publico_responsavel_transporte', 'tipo_veiculo'),
            )

            etapa_5.formulario.add_choices(
                label='Estado de Origem', name='estado_naturalidade', value=estado_naturalidade_value, choices=self.choices_estado, required=False
            ).add_choices(
                label='Naturalidade', name='naturalidade', value=naturalidade_value, choices=self.choices_cidade, required=False
            ).add_choices(label='Raça', name='raca', value='', choices=self.choices_raca, required=True)
            if etapa_2.formulario.get_value('nacionalidade') != 'Brasileira':
                etapa_5.formulario.add_choices(
                    label='País de Origem', name='pais_origem', value=pais_origem_value, choices=self.choices_pais, required=False
                )
                etapa_5.fieldsets.add(name='Outras Informações', fields=('estado_naturalidade', 'naturalidade', 'pais_origem', 'raca'))
            else:
                etapa_5.fieldsets.add(name='Outras Informações', fields=('estado_naturalidade', 'naturalidade', 'raca'))

            etapa_5.formulario.add_choices(
                label='Nível de Ensino', name='nivel_ensino_anterior', value='', choices=self.choices_nivel_ensino, required=True
            ).add_choices(
                label='Tipo da Instituição', name='tipo_instituicao_origem', value='', choices=self.choices_tipo_instituicao_origem, required=True
            ).add_choices(
                label='Ano de Conclusão', name='ano_conclusao_estudo_anterior', value='', choices=self.choices_ano, required=False
            ).add_file(
                label='Histórico/Declaração Escolar',
                name='copia_historico_escolar',
                value=None,
                label_to_file='Histórico Escolar',
                required=True,
            ).add_file(
                label='Diploma/Certificado',
                name='copia_doc_conclusao_ensino',
                value=None,
                label_to_file='Diploma/Certificado',
                required=False,
                help_text='Obrigatório quando o nível de ensino for igual ou superior ao médio.',
            )
            etapa_5.fieldsets.add(
                name='Dados Escolares Anteriores',
                fields=(
                    'nivel_ensino_anterior',
                    'tipo_instituicao_origem',
                    'ano_conclusao_estudo_anterior',
                    'copia_historico_escolar',
                    'copia_doc_conclusao_ensino',
                ),
            )

        return etapa_5

    def _get_etapa_6(self, cpf):
        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        etapa_2 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=2)
        etapa_5 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=5)
        data_nascimento = self.clear_date(etapa_2.formulario.get_value(name='data_nascimento'))
        idade = self.get_idade(data_nascimento)
        titulo_eleitor_required = 18 <= idade <= 65

        etapa_6 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=6)
        if etapa_6:
            etapa_6.formulario.set_required(name='numero_titulo_eleitor', required=titulo_eleitor_required)
            etapa_6.formulario.set_required(name='zona_titulo_eleitor', required=titulo_eleitor_required)
            etapa_6.formulario.set_required(name='secao', required=titulo_eleitor_required)
            etapa_6.formulario.set_required(name='data_emissao_titulo_eleitor', required=titulo_eleitor_required)
            etapa_6.formulario.set_required(name='uf_emissao_titulo_eleitor', required=titulo_eleitor_required)
            etapa_6.formulario.set_required(name='copia_titulo', required=titulo_eleitor_required)
            etapa_6.formulario.set_required(name='copia_quitacao_eleitoral', required=titulo_eleitor_required)
            return etapa_6

        candidato_vaga = etapa_1.formulario.get_value('candidato_vaga')
        sgc_dados_candidato = CandidatoVaga.matricula_online_dados_candidato(candidato_vaga_id=candidato_vaga)
        sgc_dados_candidato = BeautifulSoup(sgc_dados_candidato, 'xml')
        dados_pessoais = sgc_dados_candidato.dados_pessoais
        candidato_vaga_obj = CandidatoVaga.objects.get(pk=candidato_vaga)
        aprovado_quilombola = candidato_vaga_obj.candidato.aprovado_quilombola

        value = self.clear_value(dados_pessoais.rg_uf.string)
        estado_rg_value = Estado.ESTADOS.get(value.upper(), '')

        value = self.clear_value(dados_pessoais.rg_orgao.string)
        value = OrgaoEmissorRg.objects.filter(nome__iexact=value)
        orgao_rg_emissor_value = ''
        if value.exists():
            orgao_rg_emissor_value = value.first().pk

        rg_data_emissao = self.clear_date(dados_pessoais.rg_data_emissao.string)
        etapa_6 = Etapa(numero=6, total_etapas=self.get_numero_total_etapas(), nome='Etapa 6')

        etapa_6.formulario.add_string(
            label='Número do RG', name='numero_rg', value=self.clear_value(dados_pessoais.rg_numero.string), required=True
        ).add_choices(label='Estado Emissor', name='uf_emissao_rg', value=estado_rg_value, choices=self.choices_estado, required=True).add_choices(
            label='Orgão Emissor', name='orgao_emissao_rg', value=orgao_rg_emissor_value, choices=self.choices_orgao_emissao_rg, required=True
        ).add_date(label='Data de Emissão', name='data_emissao_rg', value=rg_data_emissao, mask=Mask.DATE, required=True).add_file(
            label='Cópia do RG legível', name='copia_rg', value=None, label_to_file='RG', required=True
        )
        etapa_6.fieldsets.add(name='RG', fields=('numero_rg', 'uf_emissao_rg', 'orgao_emissao_rg', 'data_emissao_rg', 'copia_rg'))

        etapa_6.formulario.add_string(label='Título de Eleitor', name='numero_titulo_eleitor', value='', required=titulo_eleitor_required).add_string(
            label='Zona', name='zona_titulo_eleitor', value='', required=titulo_eleitor_required
        ).add_string(label='Seção', name='secao', value='', required=titulo_eleitor_required).add_date(
            label='Data de Emissão',
            name='data_emissao_titulo_eleitor',
            mask=Mask.DATE,
            value='',
            required=titulo_eleitor_required,
        ).add_choices(
            label='Estado Emissor', name='uf_emissao_titulo_eleitor', value='', choices=self.choices_estado, required=titulo_eleitor_required
        ).add_file(
            label='Cópia do Título de Eleitor',
            name='copia_titulo',
            value=None,
            label_to_file='Título de Eleitor',
            required=titulo_eleitor_required,
        ).add_file(
            label='Cópia de Quitação Eleitoral',
            name='copia_quitacao_eleitoral',
            value=None,
            label_to_file='Comprovante de Quitação Eleitoral',
            required=titulo_eleitor_required,
        )
        etapa_6.fieldsets.add(
            name='Título de Eleitor',
            fields=(
                'numero_titulo_eleitor',
                'zona_titulo_eleitor',
                'secao',
                'data_emissao_titulo_eleitor',
                'uf_emissao_titulo_eleitor',
                'copia_titulo',
                'copia_quitacao_eleitoral',
            ),
        )

        sexo = etapa_2.formulario.get_value(name='sexo')
        if sexo and sexo.upper() == 'M':
            carteira_reservista_required = self.eh_obrigatorio_anexar_reservista(data_nascimento)
            etapa_6.formulario.add_string(
                label='Número do Documento Militar', name='numero_carteira_reservista', value='', required=carteira_reservista_required
            ).add_string(label='Região', name='regiao_carteira_reservista', value='', required=carteira_reservista_required).add_string(
                label='Série', name='serie_carteira_reservista', value='', required=carteira_reservista_required
            ).add_choices(
                label='Estado Emissor',
                name='estado_emissao_carteira_reservista',
                value='',
                choices=self.choices_estado,
                required=carteira_reservista_required,
            ).add_integer(
                label='Ano',
                name='ano_carteira_reservista',
                value='',
                required=carteira_reservista_required,
                min_value=1800,
                max_value=datetime.today().year,
            ).add_file(
                label='Upload do Documento Militar',
                name='copia_rervista',
                value=None,
                label_to_file='Documento Militar',
                required=carteira_reservista_required,
            )
            etapa_6.fieldsets.add(
                name='Documento Militar',
                fields=(
                    'numero_carteira_reservista',
                    'regiao_carteira_reservista',
                    'serie_carteira_reservista',
                    'estado_emissao_carteira_reservista',
                    'ano_carteira_reservista',
                    'copia_rervista',
                ),
            )

        etapa_6.formulario.add_choices(
            label='Tipo de Certidão', name='tipo_certidao', value='', choices=self.choices_tipo_certidao, required=True
        ).add_choices(label='Cartório', name='cartorio', value='', choices=self.choices_cartorio, required=False).add_string(
            label='Número de Termo', name='numero_certidao', value='', required=False
        ).add_string(label='Folha', name='folha_certidao', value='', required=False).add_string(
            label='Livro', name='livro_certidao', value='', required=False
        ).add_date(label='Data de Emissão', name='data_emissao_certidao', mask=Mask.DATE, value='', required=False).add_string(
            label='Matrícula', name='matricula_certidao', value='', required=False
        ).add_file(label='Cópia da Certidão', name='copia_certidao', value=None, label_to_file='Certidão', required=True)
        etapa_6.fieldsets.add(
            name='Certidão Civil',
            fields=(
                'tipo_certidao',
                'cartorio',
                'numero_certidao',
                'folha_certidao',
                'livro_certidao',
                'data_emissao_certidao',
                'matricula_certidao',
                'copia_certidao',
            ),
        )

        if etapa_5 and etapa_5.formulario.get_value('raca') and int(etapa_5.formulario.get_value('raca')) == Raca.ID_RACA_INDIGENA:
            etapa_6.formulario.add_choices(
                label='Povo indígena',
                name='povo_indigena',
                value='',
                choices=self.choices_povo_indigena,
                required=True,
            ).add_file(
                label='Autodeclaração indígena (Anexo VI)',
                name='autodeclaracao_indigena',
                value=None,
                label_to_file='Autodeclaração indígena',
                required=True,
            ).add_file(
                label='Pertencimento/RANI (Anexo VII)',
                name='rani_pertencimento_indigena',
                value=None,
                label_to_file='Pertencimento/RANI',
                required=True,
            )
            etapa_6.fieldsets.add(
                name='Cota Indígena',
                fields=('povo_indigena', 'autodeclaracao_indigena', 'rani_pertencimento_indigena'),
            )

        if aprovado_quilombola:
            etapa_6.formulario.add_file(
                label='Autodeclaração Quilombola (Anexo VIII)',
                name='autodeclaracao_quilombola',
                value=None,
                label_to_file='Autodeclaração Quilombola',
                required=aprovado_quilombola,
            ).add_file(
                label='Declaração de Pertencimento Quilombola',
                name='declaracao_pertencimento_quilombola',
                value=None,
                label_to_file='Pertencimento Quilombola',
                required=aprovado_quilombola,
            )
            etapa_6.fieldsets.add(
                name='Cota Quilombola',
                fields=('autodeclaracao_quilombola', 'declaracao_pertencimento_quilombola'),
            )

        return etapa_6

    def _get_etapa_7(self, cpf):
        return self._get_etapa_anexos_extras_opcionais(cpf)

    def get_numero_etapa_anexos_extras_opcionais(self):
        return 7

    def _get_etapa_8(self, cpf):
        etapa_8 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=8)

        if not etapa_8:
            etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
            etapa_5 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=5)
            candidato_vaga = etapa_1.formulario.get_value('candidato_vaga')
            sgc_dados_candidato = self.get_dados_candidato_sgc(cpf)
            candidato_vag_obj = CandidatoVaga.objects.get(pk=candidato_vaga)

            self.set_criterios(sgc_dados_candidato.inscricao)

            edital = etapa_1.formulario.get_field('candidato_vaga')
            edital = edital['choices'][int(candidato_vaga)]
            raca = etapa_5.formulario.get_field('raca')
            raca = raca['choices'][int(etapa_5.formulario.get_value('raca'))]

            instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
            programa_oferta = etapa_1.formulario.get_value('programa_convenio') or ''

            pergunta_01 = (
                f'DECLARO que sou uma pessoa <b>{raca}</b>, para o fim específico de atender '
                f'aos termos do <b>{edital}</b> no que se refere à reserva de vagas da lista '
                f'diferenciada com a condição de etnia.'
            )
            pergunta_02 = (
                f'<p>Declaro que estou ciente das normas previstas na Organização Didática* do {instituicao_sigla} e que:</p>'
                f'<ol>'
                f'<li>Devo manter frequência mínima de 75%.</li>'
                f'<li>Posso ser desligado por ausência sem justificativa no início do curso.</li>'
                f'<li>É vedada a ocupação de matrículas simultâneas em desacordo com as normas institucionais e legais.</li>'
                f'</ol>'
            )
            pergunta_03 = (
                'Declaro, também, estar ciente de que a comprovação de falsidade, em procedimento com contraditório e ampla defesa, '
                'implicará no cancelamento da matrícula e demais sanções legais cabíveis (inclusive Art. 299 do CP).'
            )
            pergunta_04 = 'Reconheço que as informações prestadas são verdadeiras.'
            pergunta_05 = 'Confirmo que após concluir o cadastro não poderei mais alterar os dados e arquivos enviados.'

            etapa_8 = Etapa(numero=8, total_etapas=self.get_numero_total_etapas(), nome='Etapa 8')

            if candidato_vag_obj.candidato.aprovado_heteroidentificacao is not True and self.criterio_etnico:
                etapa_8.formulario.add_boolean(label='Confirmo', help_text=mark_safe(pergunta_01), name='declaracao_etnia', value=None, required=True)
                etapa_8.fieldsets.add(name='Autodeclaração Étnico-Racial', fields=('declaracao_etnia',))

            etapa_8.formulario.add_boolean(label='Confirmo', help_text=mark_safe(pergunta_02), name='declaracao_didatica', value=None, required=True)
            etapa_8.fieldsets.add(name='Organização Didática', fields=('declaracao_didatica',))

            etapa_8.formulario.add_boolean(label='Confirmo', help_text=mark_safe(pergunta_03), name='declaracao_legais', value=None, required=True)
            etapa_8.fieldsets.add(name='Declarações Legais', fields=('declaracao_legais',))

            if 'PARTIUIF' in str(programa_oferta).upper():
                etapa_8.formulario.add_boolean(
                    label='Confirmo',
                    name='aceite_programa_partiuif',
                    value=None,
                    required=True,
                    help_text='Declaro ciência de que o turno/oferta do programa pode ser não coincidente com outras atividades pessoais.',
                )
                etapa_8.fieldsets.add(name='Aceites Específicos', fields=('aceite_programa_partiuif',))

            etapa_8.formulario.add_boolean(
                label='Confirmo', help_text=mark_safe(pergunta_04), name='declaracao_veracidade', value=None, required=True
            )
            etapa_8.fieldsets.add(name='Veracidade das Informações', fields=('declaracao_veracidade',))

            etapa_8.formulario.add_boolean(label='Confirmo', help_text=mark_safe(pergunta_05), name='declaracao_conclusao', value=None, required=True)
            etapa_8.fieldsets.add(name='Conclusão', fields=('declaracao_conclusao',))

        return etapa_8

    def get_dados_email(self, solicitacao):
        dados_email = []

        try:
            solicitacao_etapa2 = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=2).first()
            if solicitacao_etapa2:
                etapa2 = Etapa.load_from_json(solicitacao_etapa2.get_dados_as_json())
                edital = etapa2.formulario.get_field('edital_nome')
                dados_email.append(edital)
                edital_vaga = etapa2.formulario.get_field('edital_vaga')
                dados_email.append(edital_vaga)
                edital_lista = etapa2.formulario.get_field('edital_lista')
                dados_email.append(edital_lista)
                cpf = etapa2.formulario.get_field('cpf')
                dados_email.append(cpf)
                nome = etapa2.formulario.get_field('nome')
                dados_email.append(nome)
                email_pessoal = etapa2.formulario.get_field('email_pessoal')
                dados_email.append(email_pessoal)

            for numero_etapa in range(1, self.get_numero_total_etapas()):
                solicitacao_etapa = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=numero_etapa).first()
                if solicitacao_etapa:
                    etapa = Etapa.load_from_json(solicitacao_etapa.get_dados_as_json())
                    if etapa.formulario.get_campos_by_status(status='ERROR'):
                        dados_email += etapa.formulario.get_campos_by_status(status='ERROR')
            return dados_email
        except Exception as e:
            if settings.DEBUG:
                raise Exception(f'Detalhes: {e}')
            capture_exception(e)

        return None

    def _get_dados_edital_oferta(self, candidato_vaga):
        curso_campus = candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus
        programa = getattr(curso_campus, 'programa', None)
        campus = getattr(getattr(getattr(getattr(curso_campus, 'diretoria', None), 'setor', None), 'uo', None), 'sigla', None) or getattr(
            candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus.diretoria.setor.uo, 'sigla', None
        )
        modalidade = getattr(curso_campus, 'modalidade', None)
        turno = candidato_vaga.candidato.turno or getattr(curso_campus, 'turno', None)
        return {
            'programa': str(programa or ''),
            'campus': str(campus or ''),
            'modalidade': str(modalidade or 'Presencial'),
            'turno': str(turno or ''),
        }

    def _is_cota_renda_baixa(self, cpf):
        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        candidato_vaga = CandidatoVaga.objects.get(pk=etapa_1.formulario.get_value('candidato_vaga'))
        sgc_dados_candidato = self.get_dados_candidato_sgc(cpf)
        self.set_criterios(sgc_dados_candidato.inscricao)
        return self.criterio_social and candidato_vaga.candidato.aprovado_baixa_renda is True
