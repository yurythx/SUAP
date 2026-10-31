import base64
import logging
import re
from collections import OrderedDict
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.safestring import mark_safe
from sentry_sdk import capture_exception

from catalogo_provedor_servico.forms import CatalogoEfetuarMatriculaForm, SolicitacaoMatriculaForm
from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa, SolicitacaoEtapaArquivo, SolicitacaoHistoricoSituacao
from catalogo_provedor_servico.providers.base import AbstractBaseServiceProvider, Etapa
from catalogo_provedor_servico.utils import Notificar, format_data
from comum.models import Ano, Configuracao, Raca
from djtools import forms
from djtools.thumbs import ImageFormFieldWithThumbs
from djtools.utils import httprr
from edu.forms import EfetuarMatriculaForm
from edu.models import Aluno, Cartorio, Cidade, Deficiencia, Estado, MatrizCurso, NivelEnsino, OrgaoEmissorRg, Pais, TipoNEE
from edu.models.arquivos import AlunoArquivo
from processo_seletivo.models import CandidatoVaga, ausencia_candidato_sinal, inaptidao_candidato_sinal, matricula_candidato_sinal

logger = logging.getLogger(__name__)


class AbstractServiceProvider(AbstractBaseServiceProvider):
    pass


class AbstractMatriculaServiceProvider(AbstractServiceProvider):
    def clear_date(self, value):
        if not value:
            return None
        data = str(value).split('-')
        if len(data[0]) == 4:
            return datetime.strptime(value, '%Y-%m-%d').date()
        elif len(data[0]) == 2:
            return datetime.strptime(value, '%d-%m-%Y').date()
        return None

    def clear_value(self, value):
        if value is None or value == 'None':
            return ''
        return str(value)

    def get_candidato_vaga(self, solicitacao):
        etapa_1_dados = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1).get_dados_as_json()

        candidato_vaga = None

        for dado in etapa_1_dados['formulario']:
            if dado['name'] == 'candidato_vaga':
                candidato_vaga = dado['value']
                break

        if candidato_vaga is None:
            raise Exception('Erro ao processar requisição')

        return CandidatoVaga.objects.get(pk=candidato_vaga)

    def get_dados_candidato_sgc(self, cpf):
        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        candidato_vaga = etapa_1.formulario.get_value('candidato_vaga')
        sgc_dados_candidato = CandidatoVaga.matricula_online_dados_candidato(candidato_vaga_id=candidato_vaga)
        return BeautifulSoup(sgc_dados_candidato, 'xml')

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
                telefone_govbr = etapa2.formulario.get_field('telefone_govbr')
                dados_email.append(telefone_govbr)

            # Obtém fields com erro
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

    def get_form(self, candidato_vaga, request, etapa_atual):
        formulario = CatalogoEfetuarMatriculaForm(candidato_vaga=candidato_vaga, request=request)
        etapas = []
        for numero_etapa in range(etapa_atual.numero):
            etapas.append(self._get_etapa_para_edicao(cpf=candidato_vaga.candidato.cpf, numero_etapa=numero_etapa + 1))

        for etapa in [*etapas, etapa_atual]:
            if etapa:
                for field in etapa.formulario.campos:
                    value = field['value']
                    if field['type'] == 'date':
                        value = self.clear_date(value)

                    formulario.data[field['name']] = value
                    formulario.cleaned_data[field['name']] = value
                    # TODO Para avaliar
                    # formulario.fields[field['name']].clean(value)
        return formulario

    def get_idade(self, data_nascimento, data_para_calculo=None):
        if not isinstance(data_nascimento, datetime):
            data_nascimento = datetime(data_nascimento.year, data_nascimento.month, data_nascimento.day)
        hoje = datetime.now()
        _data_para_calculo = data_para_calculo or hoje
        num_anos = int((_data_para_calculo - data_nascimento).days / 365.25)
        return num_anos

    def eh_obrigatorio_anexar_reservista(self, data_nascimento):
        """
        Se tem 18 anos e se a data atual é menor que 30/06: só é obrigatório anexar reservista se completou 18 anos até
        31/12 do ano anterior.
        Maior de 18 anos e menor igual a 45 anos é obrigatório anexar reservista
        Se é menor de 18 anos não é obrigatório anexar reservista
        :param data_nascimento:
        :return: boolean
        """
        idade = self.get_idade(data_nascimento)
        hoje = datetime.today()
        ano_anterior = (hoje - timedelta(days=365)).year
        utimo_dia_ano_anterior = datetime(ano_anterior, 12, 31, 0, 0)
        retorno = True
        if idade == 18 and hoje.month <= 6:
            if data_nascimento.month <= 6 and not (self.get_idade(data_nascimento, utimo_dia_ano_anterior) >= 18):
                retorno = False
        elif idade < 18 or idade > 45:
            retorno = False
        return retorno

    def is_em_periodo_avaliacao(self, solicitacao, campus=None):
        se = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=1).first()
        if not se:
            return False
        for dado in se.get_dados_as_json()['formulario']:
            if dado['name'] == 'candidato_vaga':
                candidato_vaga = CandidatoVaga.objects.filter(pk=dado['value']).first()
                if not candidato_vaga:
                    return False
                edital = candidato_vaga.candidato.edital
                ver_campus = candidato_vaga.campus
                if campus is not None:
                    ver_campus = campus
                em_periodo_avaliacao = edital.em_periodo_matricula(campus=ver_campus) or edital.em_periodo_avaliacao(campus=ver_campus)
                return em_periodo_avaliacao
        return False

    # TODO: Rever com Hugo essa implementação. A ideia é o service provider não ter estado.
    # Hoje não temos problema porque a cada requisição um novo service provider é instanciado.
    # Acredito que a melhor abordagem é criar uma entidade que represente os dados da inscrição
    # do SGC e criar um método que devolva esta entidade preenchida. Nessa entidade, tentar melhorar
    # a legibilidade, tipo, ao invés "candidato_sgc.criterio_deficiencia", ficaria mais claro algo
    # do tipo "candidato_sgc.tem_deficiencia. Uma vez ajustado aqui, lembrar de replicar o ajuste
    # nos outros providers que usam a mesma informação".
    def set_criterios(self, inscricao):
        self.criterio_etnico = inscricao.lista.criterio_etnico.string == 'True'
        self.criterio_deficiencia = inscricao.lista.criterio_deficiencia.string == 'True'
        self.criterio_escola_publica = inscricao.lista.criterio_escola_publica.string == 'True'
        self.criterio_social = inscricao.lista.criterio_social.string == 'True'
        self.criterio_outros = inscricao.lista.criterio_outros.string == 'True'

    def get_numero_etapa_anexos_extras_opcionais(self):
        return None

    def pode_retornar_para_analise(self, request, solicitacao):
        pode, msg = super().pode_retornar_para_analise(request, solicitacao)
        if not pode:
            return pode, msg

        solicitacao_etapa = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=1).first()
        if not solicitacao_etapa:
            return False, 'Não é possível identificar o candidato'

        etapa = Etapa.load_from_json(solicitacao_etapa.get_dados_as_json())

        candidato_vaga_id = etapa.formulario.get_value('candidato_vaga')
        candidato_vaga = CandidatoVaga.objects.get(pk=candidato_vaga_id)
        if candidato_vaga.vaga is None:
            return False, 'Vaga do candidato já foi preenchida por outro candidato.'
        return True, ''

    def _get_etapa_anexos_extras_opcionais(self, cpf):
        numero_etapa = self.get_numero_etapa_anexos_extras_opcionais()
        etapa = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=numero_etapa)
        if etapa:
            return etapa

        etapa = Etapa(numero=numero_etapa, total_etapas=self.get_numero_total_etapas(), nome=f'Etapa {numero_etapa}')

        etapa_1 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=1)
        candidato_vaga_display_value = etapa_1.formulario.get_display_value('candidato_vaga')
        pergunta_01 = f'Estou ciente de que, caso o edital <strong>{candidato_vaga_display_value}</strong> exija outros documentos, eu devo fornecer tais documentos aqui neste etapa.'
        etapa.formulario.add_boolean(label='Confirmo', help_text=mark_safe(pergunta_01), name='declaracao_legais', value=None, required=True)
        etapa.fieldsets.add(name='Declaração de ciência', fields=('declaracao_legais',))

        # Construindo a área para o upload dos documetos que variam entre os editais de pós graduação.
        for i in range(1, 6):
            etapa.formulario.add_string(label=f'Descrição {i}', name=f'anexo_{i}_descricao', value=None, required=False, max_length=100).add_file(
                label=f'Anexo {i}', name=f'anexo_{i}_file', value=None, label_to_file=f'Anexo{i}', allowed_extensions=['pdf'], required=False
            )
            etapa.fieldsets.add(
                name=f'Anexo {i}',
                fields=(
                    f'anexo_{i}_descricao',
                    f'anexo_{i}_file',
                ),
            )

        return etapa

    def _validate_dados_etapa(self, request, etapa, solicitacao):
        if etapa.numero == 1:
            candidato_vaga = etapa.formulario.get_value('candidato_vaga')
        else:
            etapa_1 = self._get_etapa_para_edicao(cpf=solicitacao.cpf, numero_etapa=1)
            if etapa_1:
                candidato_vaga = etapa_1.formulario.get_value('candidato_vaga')
            else:
                return ['Falha ao tentar encontrar primeira etapa. Por favor, tente do início novamente.']

        if etapa.numero == 2:
            try:
                foto_codificada = etapa.formulario.get_value('foto_3x4')
                if foto_codificada:
                    binarios_foto = base64.b64decode(foto_codificada)
                    form = ImageFormFieldWithThumbs()
                    form.is_compatible(binarios_foto)
            except Exception:
                return ['Formato da foto inválido, por favor escolha outra foto.']

        candidato_vaga = CandidatoVaga.objects.filter(pk=candidato_vaga).first()

        if not candidato_vaga:
            return ['Candidato inexistente, inativar esta solicitação.']

        form_matricula = self.get_form(candidato_vaga=candidato_vaga, request=request, etapa_atual=etapa)

        # As variáveis comentadas abaixo foram uma tentativa de devolver um dicionário com os erros de validação
        # encontrados do lado provedor, para exibir o erro diretamente no campo em questão.
        # Comentei temporariamente pois algumas validações do wizard do Edu tem que ser revistas.
        # Ex: Caso o aluno seja ESTRANGEIRO, ao inves de vir uma mensagem de erro citando o campo "passaporte",
        # está vindo uma mensagem de erro do campo "nacionalidade".
        has_errors = super()._validate_dados_etapa(request, etapa, solicitacao)
        for field in etapa.formulario.campos:
            # field_errors = []
            try:
                matricula_field = form_matricula.original_fields.get(field['name'], None)
                if hasattr(matricula_field, 'clean'):
                    value = field['value']
                    if value:
                        if type(matricula_field) in [forms.DateFieldPlus, forms.DateField]:
                            value = datetime.strptime(value, '%Y-%m-%d').date()
                        elif (
                            type(matricula_field) in [forms.MultipleModelChoiceFieldPlus, forms.MultipleModelChoiceField] and type(value) is not list
                        ):
                            value = [value]
                    matricula_field.clean(value)
            except ValidationError as e:
                has_errors.append(f'<b>{field["label"]} (suap.edu)</b> - {e.messages[0]}')
                # field_errors.append(e.messages[0])

            if hasattr(form_matricula, f'clean_{field["name"]}'):
                try:
                    getattr(form_matricula, f'clean_{field["name"]}')()
                except ValidationError as e:
                    has_errors.append(f'<b>{field["label"]} (suap.edu)</b> - {e.messages[0]}')
                    # field_errors.append(e.messages[0])
            # if field_errors:
            #     has_errors[field['name']] = field_errors

        # Caso seja a etapa dos anexos extras opcionais, a rotina abaixo garante que cada anexo
        # informado tenha uma descrição e vice-versa.
        numero_etapa_anexos_extras_opcionais = self.get_numero_etapa_anexos_extras_opcionais()
        if numero_etapa_anexos_extras_opcionais and etapa.numero == numero_etapa_anexos_extras_opcionais:
            for i in range(1, 6):
                anexo_descricao_field = etapa.formulario.get_field(f'anexo_{i}_descricao')
                anexo_file_field = etapa.formulario.get_field(f'anexo_{i}_file')

                anexo_and_descricao_informados = 0
                if anexo_descricao_field['value']:
                    anexo_and_descricao_informados += 1
                if anexo_file_field['value'] or anexo_file_field['value_hash_sha512_link_id']:
                    anexo_and_descricao_informados += 1

                # Se anexo_and_descricao_informados for igual a 1, é sinal de que apenas parte da informação do anexo
                # em questão foi fornecida. Nesse caso, iremos cobrar que toda a informação seja fornecida.
                if anexo_and_descricao_informados == 1:
                    has_errors.append(f'Ao informar o <b>Anexo {i}</b>, você precisa fornecer uma descrição e fazer o upload do arquivo.')

        return has_errors

    def executar_solicitacao(self, request, solicitacao):
        title = 'Executar Solicitação'
        etapa_1_dados = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1).get_dados_as_json()

        candidato_vaga = None

        for dado in etapa_1_dados['formulario']:
            if dado['name'] == 'candidato_vaga':
                candidato_vaga = dado['value']
                break

        if candidato_vaga is None:
            raise Exception('Erro ao processar requisição')

        # TODO: Toda a inteligência para chamar SolicitacaoMatriculaForm praticamente está na variável canditado_vaga.
        # Não seria interessante deixar tudo isso dentro do form?
        candidato_vaga = CandidatoVaga.objects.filter(pk=candidato_vaga).first()

        if candidato_vaga is None:
            raise Exception('Erro ao processar requisição, candidato inexistente')

        qs_matriz_curso = MatrizCurso.objects.filter(curso_campus=candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus).order_by('-id')
        ano_letivo = candidato_vaga.candidato.edital.ano_id
        periodo_letivo = candidato_vaga.candidato.edital.semestre
        turno = candidato_vaga.candidato.turno and candidato_vaga.candidato.turno_id or None
        forma_ingresso = candidato_vaga.oferta_vaga.lista.forma_ingresso and candidato_vaga.oferta_vaga.lista.forma_ingresso.pk or None
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
                            if field['type'] == 'boolean':
                                value = field['value']
                            else:
                                value = False

                        if field['type'] == 'date':
                            value = format_data(value)

                        if field['name'] == 'cidade' and value:
                            cidade = Cidade.objects.filter(pk=value).first()
                            if cidade:
                                data_post['estado'] = str(cidade.estado_id)

                        if field['name'] == 'naturalidade' and value:
                            cidade = Cidade.objects.filter(pk=value).first()
                            if cidade:
                                data_post['estado_naturalidade'] = str(cidade.estado_id)

                        if field['name'] == 'telefone_principal' and not value:
                            for field_telefone_govbr in etapa.get_dados_as_json()['formulario']:
                                if field_telefone_govbr['name'] == 'telefone_govbr':
                                    value = field_telefone_govbr['value']

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

                        # Verificando se o provider tem uma etapa de anexos extras opcionais. Caso exista, a descrição informada
                        # pelo candidato será levada em conta na hora de adicionar os arquivos em sua "pasta de documentos".
                        solicitacao_etapa_anexos_extras_opcionais = None
                        etapa_anexos_extras_opcionais = None
                        numero_etapa_anexos_extras_opcionais = self.get_numero_etapa_anexos_extras_opcionais()
                        if self.get_numero_etapa_anexos_extras_opcionais():
                            solicitacao_etapa_anexos_extras_opcionais = SolicitacaoEtapa.objects.get(
                                solicitacao=solicitacao, numero_etapa=numero_etapa_anexos_extras_opcionais
                            )
                            etapa_anexos_extras_opcionais = Etapa.load_from_json(solicitacao_etapa_anexos_extras_opcionais.get_dados_as_json())

                        # Fazendo o registro de todos os documentos enviados pelo aluno, durante a matrícula, na sua "pasta de documentos".
                        solicitacao_etapa_arquivos = SolicitacaoEtapaArquivo.objects.filter(solicitacao_etapa__solicitacao=solicitacao)
                        if solicitacao_etapa_arquivos.exists():
                            for sea in solicitacao_etapa_arquivos:
                                aluno_arquivo = AlunoArquivo()

                                observacao = 'Documento fornecido pelo aluno durante matrícula online'
                                if len(observacao) > 255:
                                    observacao = f'{observacao[:250]} ...'
                                aluno_arquivo.observacao = observacao
                                aluno_arquivo.tipo_origem_cadastro = AlunoArquivo.TIPO_ORIGEM_CADASTRO_MATRICULA_ONLINE

                                aluno_arquivo.aluno = aluno
                                aluno_arquivo.arquivo_unico = sea.arquivo_unico
                                aluno_arquivo.nome_original = sea.nome_original

                                # Caso os arquivos em questão sejam da etapa de anexos extras opcionais, vamos pegar
                                # a descrição imformada pelo usuário para poder exibir uma informação amigável na
                                # sua Pasta Documental e também para nomear o arquivo.
                                # Ex: Exibir "Termo de Compromisso do Candidato" ao invés de "Anexo 1".
                                if (
                                    numero_etapa_anexos_extras_opcionais
                                    and sea.solicitacao_etapa.numero_etapa == numero_etapa_anexos_extras_opcionais
                                ):
                                    anexo_extensao = '.{}'.format(sea.nome_original.split('.')[-1])
                                    anexo_numero = int(sea.nome_atributo_json.replace('anexo_', '').replace('_file', ''))
                                    anexo_descricao = etapa_anexos_extras_opcionais.formulario.get_value(f'anexo_{anexo_numero}_descricao')

                                    # No caso do nome de exibição do arquivo o seu limite é 50, contando com a extensão
                                    # do arquivo.
                                    # Deixando o nome no padrão "Camel Case", apenas letras e números e sem espaços. Obs:
                                    # Fiz isso pensando em fechar possível brecha que permitisse a execução de um comando
                                    # malicioso durante a criação do arquivo em disco.
                                    # Ex: A descrição do arquivo, fornercida pelo usuário, ser algo do tipo "rm /bin".
                                    nome_exibicao_ajustado = re.sub('[\\W_]+', '', anexo_descricao.title())
                                    # Limitando o nome a 50 caracteres no total, contando a extensão.
                                    nome_exibicao_ajustado = nome_exibicao_ajustado[: 50 - len(anexo_extensao)]
                                    aluno_arquivo.nome_exibicao = f'{nome_exibicao_ajustado}{anexo_extensao}'

                                    # Deixando o nome no padrão "Camel Case", apenas letras e números e espaços simples.
                                    aluno_arquivo.descricao = re.sub('[\\W_]+', ' ', anexo_descricao.title())
                                else:
                                    aluno_arquivo.nome_exibicao = sea.nome_exibicao
                                    aluno_arquivo.descricao = sea.descricao

                                aluno_arquivo.data_hora_upload = sea.data_hora_upload
                                aluno_arquivo.tipo = AlunoArquivo.get_tipo_para_matricula_online(sea.descricao)

                                aluno_arquivo.data_validacao = aluno_arquivo.data_hora_upload
                                aluno_arquivo.prazo_validade = aluno_arquivo.prazo_validade or 6
                                aluno_arquivo.data_expiracao = aluno_arquivo.data_validacao.date() + relativedelta(years=aluno_arquivo.prazo_validade)

                                aluno_arquivo.save()
                                solicitacao.add_dado_registro_execucao(model_object=aluno_arquivo, operation='CREATE')

                        # Registra solicitação com ATENDIDA.
                        solicitacao.status = Solicitacao.STATUS_ATENDIDO
                        # Esse status será enviado pra o aluno.
                        solicitacao.status_detalhamento = 'Matrícula realizada com sucesso.'

                        # Em tese, a chamada abaixo deveria ser feita sem problemas, contudo caso ela seja feita, o save
                        # da solicitação vai disparar a exceção do clean de Solicitacao.
                        # Isso ocorre porque o status da solicitacao, no banco, antes do save, ainda será PRONTO_PRA_EXECUCAO,
                        # daí ao chamar esse método abaixo, ocorrerá um primeiro save da solicitação e, consequentemente,
                        # o save da linha seguinte será um segundo save, disparando assim a exceção defininda do clean de Solicitacao.
                        # Estou achando a ordem das coisas bastante confusa, e também a legibilidade do método "matricular_solicitacoes",
                        # disparado pelo sinal "matricula_candidato_sinal".
                        # TODO: Reunir com a equipe pra rever o funcionamento disso e dar uma geral nos providers, visando tentar deixar
                        # a evoluçao/manutenção mais fácil de ser realizada.
                        # candidato_vaga.registrar_matricula()
                        solicitacao.add_dado_registro_execucao(model_object=candidato_vaga, operation='UPDATE')

                        solicitacao.save()

                        # Registrando a matricula do aluno junto ao módulo de processo seletivo
                        candidato_vaga.registrar_matricula()

                        # Adicionando link pra matrícula detalhamento, sem executar o save da solicitacao.
                        # Isso aparecerá só para o avaliador, na tela de avaliação.
                        Solicitacao.objects.filter(pk=solicitacao.pk).update(
                            status_detalhamento=f'Matrícula <a href="/edu/aluno/{aluno.matricula}">{aluno.matricula}</a> realizada com sucesso.'
                        )

                        # Registra acomapanhamento e indica conclusão do serviço junto ao GOVBR
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


def get_solicitacao_por_candidato_vaga(solicitacoes, candidato_vaga_id):
    # Obtém a solicitação correta a partir do id do candidato vaga
    for obj in solicitacoes:
        etapa = SolicitacaoEtapa.objects.filter(numero_etapa=1, solicitacao=obj).first()
        candidato_vaga_solicitacao = etapa and etapa.get_dados_as_json()['formulario'][0]['value'] or '-'
        if str(candidato_vaga_id) == str(candidato_vaga_solicitacao):
            return obj


def get_servico_id_matricula(curso_campus, campus_zl_id):
    nivel_ensino = curso_campus.modalidade.nivel_ensino.id
    campus = curso_campus.diretoria.setor.uo.id

    if nivel_ensino == NivelEnsino.MEDIO:
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_tecnico') or 0)
    if nivel_ensino == NivelEnsino.GRADUACAO:
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_superior') or 0)
    if nivel_ensino == NivelEnsino.POS_GRADUACAO:
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_pos_graduacao') or 0)
    if nivel_ensino == NivelEnsino.FUNDAMENTAL and campus == campus_zl_id:
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_ead') or 0)
    if nivel_ensino == NivelEnsino.FUNDAMENTAL and campus != campus_zl_id:
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_fic') or 0)
    return None


def ausentar_solicitacoes(sender, candidato_vaga_id, desfazer=False, **kwargs):
    campus_zl_id = int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'id_campus_ead') or 0)
    if sender == CandidatoVaga:
        try:
            candidato_vaga = CandidatoVaga.objects.filter(pk=candidato_vaga_id).first()
            curso_campus = candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus
            servico_id = get_servico_id_matricula(curso_campus=curso_campus, campus_zl_id=campus_zl_id)

            solicitacoes = Solicitacao.objects.filter(cpf=candidato_vaga.candidato.cpf)

            if servico_id:
                solicitacoes = solicitacoes.filter(servico__id_servico_portal_govbr=servico_id)
                # Coloquei dentro do IF para essa ação não impactar em outros serviços
                if not desfazer:
                    solicitacao = get_solicitacao_por_candidato_vaga(
                        solicitacoes.exclude(status__in=Solicitacao.STATUS_DEFINITIVOS).order_by('id'), candidato_vaga_id
                    )
                    if solicitacao:
                        solicitacao.status = Solicitacao.STATUS_EXPIRADO
                        solicitacao.status_detalhamento = 'A solicitação de matrícula do candidato foi expirada.'
                        solicitacao.save()
                else:
                    solicitacao = get_solicitacao_por_candidato_vaga(
                        solicitacoes.filter(status=Solicitacao.STATUS_EXPIRADO).order_by('id'), candidato_vaga_id
                    )
                    if solicitacao:
                        status = solicitacao.solicitacaohistoricosituacao_set.exclude(status__in=Solicitacao.STATUS_DEFINITIVOS).latest('id').status
                        qs = Solicitacao.objects.filter(pk=solicitacao.pk)
                        qs.update(
                            status=status, status_detalhamento='A Expiração da solicitação foi desfeita.'
                        )  # precisa ser feita via update pois o save impede
                        obj = qs.first()  # solicitacao recarregada
                        SolicitacaoHistoricoSituacao.objects.create(
                            solicitacao=obj, status_detalhamento=obj.status_detalhamento, status=status, vinculo_responsavel=obj.vinculo_responsavel
                        )

        except Exception as e:
            capture_exception(e)


ausencia_candidato_sinal.connect(ausentar_solicitacoes)


# TODO: Conversa com Hugo para entender esse método.
def matricular_solicitacoes(sender, candidato_vaga_id, desfazer=False, **kwargs):
    campus_zl_id = int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'id_campus_ead') or 0)
    if sender == CandidatoVaga:
        try:
            candidato_vaga = CandidatoVaga.objects.filter(pk=candidato_vaga_id).first()
            curso_campus = candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus
            servico_id = get_servico_id_matricula(curso_campus=curso_campus, campus_zl_id=campus_zl_id)

            solicitacoes = Solicitacao.objects.filter(cpf=candidato_vaga.candidato.cpf)

            aluno = Aluno.objects.filter(candidato_vaga=candidato_vaga).first()
            if servico_id:
                solicitacoes = solicitacoes.filter(servico__id_servico_portal_govbr=servico_id)
                # Coloquei dentro do IF para essa ação não impactar em outros serviços
                if not desfazer:
                    solicitacao = get_solicitacao_por_candidato_vaga(
                        solicitacoes.exclude(status__in=Solicitacao.STATUS_DEFINITIVOS).order_by('id'), candidato_vaga_id
                    )
                    if solicitacao:
                        # Registra solicitação com ATENDIDA
                        solicitacao.status = Solicitacao.STATUS_ATENDIDO
                        solicitacao.status_detalhamento = (
                            f'Matrícula <a href="/edu/aluno/{aluno.matricula}">{aluno.matricula}</a> realizada com sucesso.'
                        )
                        solicitacao.save()

                        # Adicionando link pro aluno no detalhamento sem executar o save da solicitacao
                        Solicitacao.objects.filter(pk=solicitacao.pk).update(
                            status_detalhamento=f'Matrícula <a href="/edu/aluno/{aluno.matricula}">{aluno.matricula}</a> realizada com sucesso.'
                        )

                else:
                    solicitacao = get_solicitacao_por_candidato_vaga(
                        solicitacoes.filter(status=Solicitacao.STATUS_ATENDIDO).order_by('id'), candidato_vaga_id
                    )
                    if solicitacao:
                        status = solicitacao.solicitacaohistoricosituacao_set.exclude(status__in=Solicitacao.STATUS_DEFINITIVOS).latest('id').status
                        qs = Solicitacao.objects.filter(pk=solicitacao.pk)
                        qs.update(
                            status=status, status_detalhamento='O atendimento da solicitação foi desfeito.'
                        )  # precisa ser feita via update pois o save impede
                        obj = qs.first()  # solicitacao recarregada
                        SolicitacaoHistoricoSituacao.objects.create(
                            solicitacao=obj, status_detalhamento=obj.status_detalhamento, status=status, vinculo_responsavel=obj.vinculo_responsavel
                        )

        except Exception as e:
            capture_exception(e)


matricula_candidato_sinal.connect(matricular_solicitacoes)


def tornar_inaptas_solicitacoes(sender, candidato_vaga_id, desfazer=False, **kwargs):
    campus_zl_id = int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'id_campus_ead') or 0)
    if sender == CandidatoVaga:
        try:
            candidato_vaga = CandidatoVaga.objects.filter(pk=candidato_vaga_id).first()
            curso_campus = candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus
            servico_id = get_servico_id_matricula(curso_campus=curso_campus, campus_zl_id=campus_zl_id)

            solicitacoes = Solicitacao.objects.filter(cpf=candidato_vaga.candidato.cpf)

            if servico_id:
                solicitacoes = solicitacoes.filter(servico__id_servico_portal_govbr=servico_id)
                # Coloquei dentro do IF para essa ação não impactar em outros serviços
                if not desfazer:
                    solicitacao = get_solicitacao_por_candidato_vaga(
                        solicitacoes.exclude(status__in=Solicitacao.STATUS_DEFINITIVOS).order_by('id'), candidato_vaga_id
                    )
                    if solicitacao:
                        solicitacao.status = Solicitacao.STATUS_NAO_ATENDIDO
                        solicitacao.status_detalhamento = 'A solicitação de matrícula do candidato não foi atendida.'
                        solicitacao.save()
                else:
                    solicitacao = get_solicitacao_por_candidato_vaga(
                        solicitacoes.filter(status=Solicitacao.STATUS_NAO_ATENDIDO).order_by('id'), candidato_vaga_id
                    )
                    if solicitacao:
                        status = solicitacao.solicitacaohistoricosituacao_set.exclude(status__in=Solicitacao.STATUS_DEFINITIVOS).latest('id').status
                        qs = Solicitacao.objects.filter(pk=solicitacao.pk)
                        qs.update(
                            status=status, status_detalhamento='O não atendimento da solicitação foi desfeito.'
                        )  # precisa ser feita via update pois o save impede
                        obj = qs.first()  # solicitacao recarregada
                        SolicitacaoHistoricoSituacao.objects.create(
                            solicitacao=obj, status_detalhamento=obj.status_detalhamento, status=status, vinculo_responsavel=obj.vinculo_responsavel
                        )

        except Exception as e:
            capture_exception(e)


inaptidao_candidato_sinal.connect(tornar_inaptas_solicitacoes)


class BasicoChoicesMixin:
    @staticmethod
    def choices_sim_nao():
        return {'Sim': 'Sim', 'Não': 'Não'}

    @staticmethod
    def choices_ano():
        ano_atual = datetime.now().year
        return Ano.objects.filter(ano__lte=ano_atual).order_by('-ano')


class DocumentoChoicesMixin:
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


class EnderecoChoicesMixin:
    @staticmethod
    def choices_estado():
        return Estado.objects.all()

    @staticmethod
    def choices_cidade():
        return Cidade.objects.all()

    @staticmethod
    def choices_pais():
        return Pais.objects.all().exclude(nome='Brasil')

    @staticmethod
    def choices_zona_residencial():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_ZONA_RESIDENCIAL_CHOICES:
            choices[k] = v
        return choices


class EnsinoChoicesMixin:
    @staticmethod
    def choices_nivel_ensino():
        return NivelEnsino.objects.exclude(pk=NivelEnsino.FUNDAMENTAL)

    @staticmethod
    def choices_tipo_instituicao_origem(filters):
        tipo_instituicao = Aluno.TIPO_INSTITUICAO_ORIGEM_CHOICES
        if filters['criterio_escola_publica']:
            tipo_instituicao = [['Pública', 'Pública']]

        choices = OrderedDict()
        for k, v in tipo_instituicao:
            choices[k] = v
        return choices


class NecessidadesEspeciaisChoicesMixin:
    @staticmethod
    def choices_necessidade_especial(filters):
        if filters['criterio_deficiencia']:
            return {'Sim': 'Sim'}
        return {'Sim': 'Sim', 'Não': 'Não'}

    @staticmethod
    def choices_deficiencias():
        return Deficiencia.objects.filter(ativo=True)

    @staticmethod
    def choices_outras_nees():
        return TipoNEE.objects.filter(ativo=True)


class PessoalChoicesMixin:
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
    def choices_tipo_sanguineo():
        choices = OrderedDict()
        for k, v in Aluno.TIPO_SANGUINEO_CHOICES:
            choices[k] = v
        return choices

    @staticmethod
    def choices_raca(filters):
        if filters['criterio_etnico']:
            return Raca.objects.filter(descricao__in=['Parda', 'Preta', 'Indígena'])
        return Raca.objects.all()


class TransporteChoicesMixin:
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


class VagaChoicesMixin:
    @staticmethod
    def choices_candidatos_vaga(filters):
        candidato_vagas = CandidatoVaga.matricula_online_disponibilidade(**filters)
        choices = []
        for obj in candidato_vagas:
            choices.append((obj['candidato_vaga_id'], obj['edital_descricao']))
        return dict(choices)
