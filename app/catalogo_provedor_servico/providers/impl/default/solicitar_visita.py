import base64
import io
import os
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.utils.html import mark_safe
from redis.exceptions import LockError
from sentry_sdk import capture_exception

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa, SolicitacaoEtapaArquivo
from catalogo_provedor_servico.providers.base import Etapa, GovBr_User_Info, Mask, ValidationException
from catalogo_provedor_servico.utils import Notificar
from comum.models import APIExterna, Configuracao, JustificativaUsuarioExterno, PrestadorServico, Vinculo
from comum.types import PessoaFisicaCadastro, PrestadorServicoCadastro
from djtools.utils import atomic, cpf_valido, get_ldap_conf, httprr, mask_cpf
from edu.models import Cidade
from portaria.forms import SolicitacaoEntradaBalcaoDigitalForm
from rh.models import UnidadeOrganizacional

from .base import AbstractServiceProvider


def _ler_planilha(origem: Any) -> pd.DataFrame:
    """Lê a planilha de visitantes como texto, para o Excel não transformar o CPF em número e comer o zero à esquerda."""
    return pd.read_excel(origem, dtype=str)


def _normalizar_cpf(valor: object) -> str:
    """Remove a máscara do CPF e devolve o zero à esquerda de quem digitou só números (``zfill`` não mexe em valor mais longo)."""
    cpf = str(valor).strip().replace('.', '').replace('-', '')
    return cpf.zfill(11) if cpf.isdigit() else cpf


class SolicitarVisitaServiceProvider(AbstractServiceProvider):
    def get_id_servico_portal_govbr(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_solicitacao_visita') or 0)

    def has_cpf_column(self, df):
        cols = [str(c).strip().lower() for c in df.columns]
        return 'cpf' in cols

    def get_cpf_series(self, df):
        mapping = {str(c).strip().lower(): c for c in df.columns}
        key = mapping.get('cpf')
        return df[key] if key is not None else None

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
            objetivo = etapa.formulario.get_value('objetivo')
            if not objetivo:
                has_errors.append('Objetivo é um campo obrigatório.')
            campus = etapa.formulario.get_value('campus')
            if not campus:
                has_errors.append('Campus é um campo obrigatório.')

            has_errors += self._validar_datas(etapa)
            has_errors += self._validar_lista_visitantes(etapa, solicitacao)

        return has_errors

    def _validar_datas(self, etapa: Etapa) -> list[str]:
        """Exige as duas datas em ``AAAA-MM-DD`` e, com ambas válidas, recusa entrada anterior a hoje, saída anterior à entrada e saída acima de 31 dias (erros de campo)."""
        has_errors: list[str] = []
        datas: dict[str, datetime] = {}
        for nome, label in (('data_entrada', 'Data de Entrada'), ('data_saida', 'Data de Saída')):
            valor = etapa.formulario.get_value(nome)
            if not valor:
                has_errors.append(f'{label} é um campo obrigatório.')
                continue
            try:
                datas[nome] = datetime.strptime(valor, '%Y-%m-%d')
            except TypeError, ValueError:
                has_errors.append(f'{label} inválida.')
        # ``date.today()`` é a data local do SUAP: USE_TZ=False e TIME_ZONE=America/Recife (o Django ajusta o TZ do processo).
        if 'data_entrada' in datas and datas['data_entrada'].date() < date.today():
            has_errors.append('A data de entrada não pode ser anterior a hoje.')
        if len(datas) == 2:
            if datas['data_saida'] < datas['data_entrada']:
                has_errors.append('A data de saída não pode ser anterior à data de entrada.')
            elif datas['data_saida'] > datas['data_entrada'] + timedelta(days=31):
                has_errors.append('A data de saída deve ser no máximo 31 dias após a data de início.')
        return has_errors

    def _visita_em_grupo(self, solicitacao: Solicitacao) -> bool:
        """Lê ``visita_grupo`` da etapa 1 já salva; sem etapa 1 persistida não há como saber, então a regra do grupo não se aplica."""
        solicitacao_etapa_1 = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=1).first()
        if not solicitacao_etapa_1:
            return False
        return bool(Etapa.load_from_json(solicitacao_etapa_1.get_dados_as_json()).formulario.get_value('visita_grupo'))

    def _validar_lista_visitantes(self, etapa: Etapa, solicitacao: Solicitacao) -> list[str]:
        """Valida a planilha da etapa 2: opcional na visita individual, obrigatória na visita em grupo."""
        lista_visitantes_base64 = etapa.formulario.get_value('lista_visitantes')
        if not lista_visitantes_base64:
            if self._visita_em_grupo(solicitacao):
                return ['Para visita em grupo, é necessário anexar a lista de visitantes.']
            return []
        return self._validar_planilha(_ler_planilha(io.BytesIO(base64.b64decode(lista_visitantes_base64))))

    def _validar_planilha(self, df: pd.DataFrame) -> list[str]:
        """Valida colunas obrigatórias, células vazias e CPFs da planilha de visitantes."""
        has_errors: list[str] = []
        # Remove linhas que são completamente vazias antes da validação
        df.dropna(how='all', inplace=True)

        if not self.has_cpf_column(df):
            has_errors.append('O arquivo deve conter a coluna `CPF`.')
            return has_errors

        # Validação de dados no DataFrame
        required_cols = ['CPF', 'Nome', 'Email']
        for col in required_cols:
            if col not in df.columns:
                has_errors.append(f'A coluna obrigatória `{col}` não foi encontrada no arquivo.')
                # Interrompe a validação se uma coluna principal estiver faltando
                return has_errors

        # Verifica se há valores nulos nas colunas obrigatórias
        if df[required_cols].isnull().values.any():
            has_errors.append('As colunas `CPF`, `Nome` e `Email` não podem conter valores vazios.')

        cpfs = self.get_cpf_series(df).dropna().astype(str)
        cpfs_invalidos = [cpf for cpf in cpfs if not cpf_valido(_normalizar_cpf(cpf))]
        if cpfs_invalidos:
            has_errors.append(f'Os seguintes CPFs são inválidos: {", ".join(cpfs_invalidos)}')
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
                # Obtém fields com erro da etapa 1 caso exista
                dados_email += etapa1.formulario.get_campos_by_status(status='ERROR')
                solicitacao_etapa2 = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=2).first()
                # Obtém fields com erro da etapa 2 caso exista
                if solicitacao_etapa2:
                    etapa2 = Etapa.load_from_json(solicitacao_etapa2.get_dados_as_json())
                    dados_email += etapa2.formulario.get_campos_by_status(status='ERROR')
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
            raise ValidationException('Primeira etapa não encontrada, por favor inicie a solicitação novamente.')
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

        etapa_1 = Etapa(numero=1, total_etapas=self.get_numero_total_etapas(), nome='Etapa 1')

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

        visita_grupo = '<b style="font-size:1.5em">Será uma visita de um grupo de pessoas?</b>'

        etapa_1.formulario.add_boolean(label='Sim', help_text=mark_safe(visita_grupo), name='visita_grupo', value=False, required=False)
        etapa_1.fieldsets.add(name='Visita em grupo?', fields=('visita_grupo',))

        return etapa_1

    def _get_etapa_2(self, cpf):
        etapa_2 = self._get_etapa_para_edicao(cpf=cpf, numero_etapa=2)
        if etapa_2:
            return etapa_2

        etapa_2 = Etapa(numero=2, total_etapas=self.get_numero_total_etapas(), nome='Etapa 2')
        (
            etapa_2.formulario.add_string(label='Objetivo da visita', name='objetivo', value=None, required=True, max_length=100)
            .add_choices(label='Campus', name='campus', value=None, choices=self.choices_unidade_organizacional, required=True)
            .add_date(label='Data de Entrada', name='data_entrada', value=None, mask=Mask.DATE, required=True)
            .add_date(label='Data de Saída', name='data_saida', value=None, mask=Mask.DATE, required=True)
            .add_boolean(
                label='Confirmo',
                help_text=mark_safe('Será necessário a utilização de computadores?'),
                name='criar_usuario_ad',
                value=False,
                required=False,
            )
        )
        etapa_2.fieldsets.add(name='Dados do Requerimento', fields=('objetivo', 'campus', 'data_entrada', 'data_saida', 'criar_usuario_ad'))
        path_modelo = os.path.join(settings.BASE_DIR, '/static/portaria/ListaVisitantes.xlsx')
        modelo_url = f'{settings.SITE_URL}{path_modelo}'
        etapa_2.formulario.add_file(
            label='Documento Complementar',
            name='documento_complementar',
            help_text=mark_safe('Anexe um documento que comprove ou justifique esta solicitação (ex.: Ofício, Memorando).'),
            value=None,
            label_to_file='Documento Complementar',
            allowed_extensions=['pdf'],
            required=False,
        )
        etapa_2.formulario.add_file(
            label='Lista de Visitantes',
            name='lista_visitantes',
            help_text=mark_safe(f"A lista deve ser preenchida de acordo com o modelo <a href='{modelo_url}''>Baixar modelo</a>"),
            value=None,
            label_to_file='Lista de Visitantes',
            allowed_extensions=['xlsx'],
            required=False,
        )
        etapa_2.fieldsets.add(
            name='Anexos',
            fields=(
                'documento_complementar',
                'lista_visitantes',
            ),
        )

        return etapa_2

    def _obter_arquivo_lista(self, etapa_2: Etapa, solicitacao: Solicitacao) -> SolicitacaoEtapaArquivo | None:
        """Devolve a planilha de visitantes enviada na etapa 2, ou ``None`` quando o solicitante não a enviou."""
        if not etapa_2.formulario.get_field('lista_visitantes'):
            return None
        return SolicitacaoEtapaArquivo.objects.filter(solicitacao_etapa__solicitacao=solicitacao, nome_atributo_json='lista_visitantes').first()

    def _montar_df_visitantes(self, arquivo_lista: SolicitacaoEtapaArquivo | None, etapa_1: Etapa) -> pd.DataFrame:
        """Lê a planilha (se houver) e acrescenta o solicitante, descartando linhas sem CPF, nome ou e-mail."""
        if arquivo_lista:
            arquivo_lista.arquivo_unico.conteudo.seek(0)
            df = _ler_planilha(arquivo_lista.arquivo_unico.conteudo)
        else:
            df = pd.DataFrame(columns=['CPF', 'Nome', 'Email'])

        # Adiciona o solicitante no df para criação do usuário
        new_row = {
            'CPF': etapa_1.formulario.get_value('cpf').replace('.', '').replace('-', ''),
            'Nome': etapa_1.formulario.get_value('nome'),
            'Email': etapa_1.formulario.get_value('email'),
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        # Remove linhas onde CPF, Nome ou Email são nulos para evitar IntegrityError
        df.dropna(subset=['CPF', 'Nome', 'Email'], inplace=True)
        df['CPF'] = df['CPF'].map(_normalizar_cpf)
        return df

    def _fechar_arquivo_lista(self, arquivo_lista: SolicitacaoEtapaArquivo | None) -> None:
        if arquivo_lista:
            arquivo_lista.arquivo_unico.conteudo.close()

    def _cadastrar_visitante(self, row: pd.Series, criar_usuario_ad: bool, data_saida: str) -> None:
        """Cadastra o visitante como usuário externo, a menos que já exista prestador com o CPF."""
        cpf = _normalizar_cpf(row['CPF'])
        nome = row['Nome']
        email = row['Email']
        api = APIExterna.PESSOAFISICA
        service = api.get_service()
        if not api.ativo:
            raise ValidationError('API de pessoa física não está ativa ou não possui cache.')
        sucesso, dados_cidadao = service.get_dados_pessoais(cpf)
        sexo = {1: 'M', 2: 'F', 3: None}
        if sucesso:
            dados_cidadao = dados_cidadao[0]
        else:
            raise ValidationError(f'Não foi possível obter os dados do cidadão para o CPF {cpf}. Detalhes: {dados_cidadao}')
        pessoa_fisica: PessoaFisicaCadastro = {
            'cpf': dados_cidadao.get('CPF', None),
            'nome_registro': dados_cidadao.get('Nome', None) or nome,
            'email_secundario': email,
            'email': email,
            'nome_pai': dados_cidadao.get('NomePai', None),
            'nome_mae': dados_cidadao.get('NomeMae', None),
            'sexo': str(sexo.get(dados_cidadao.get('Sexo'))),
            'nascimento_data': datetime.strptime(dados_cidadao.get('DataNascimento'), '%Y%m%d'),
        }
        justificativa_cadastro, _ = JustificativaUsuarioExterno.objects.get_or_create(justificativa='Visitante')
        dados: PrestadorServicoCadastro = {
            'pessoa_fisica': pessoa_fisica,
            'justificativa_cadastro': justificativa_cadastro,
            'ativo': False,
        }

        if PrestadorServico.objects.filter(pessoa_fisica__cpf__in={mask_cpf(cpf), cpf}).exists():
            return
        prestador = PrestadorServico.update_or_create(dados, enviar_email=False)['prestador']
        prestador.autocadastro_em = datetime.now()
        prestador.usuario_externo = True
        prestador.save()

        # Se deve criar usuario no AD
        if not settings.DEBUG and criar_usuario_ad:
            self._criar_usuario_ad(prestador, data_saida)

    def _criar_usuario_ad(self, prestador: PrestadorServico, data_saida: str) -> None:
        prestador.ativar()
        # Cria o usuario no AD
        ldap_conf = get_ldap_conf()
        if not ldap_conf or not ldap_conf.has_write_permission():
            raise ValidationError('Erro ao tentar conectar com servidor de LDAP.')

        ldap_conf.sync_user(prestador)

        data_expiracao = datetime.strptime(data_saida, '%Y-%m-%d') + timedelta(days=30)
        ldap_conf.extend_user_expiration_date(prestador.matricula, data_expiracao)

    def executar_solicitacao(self, request: HttpRequest, solicitacao: Solicitacao) -> HttpResponse | dict[str, Any]:
        """

        :param request: Dados do request
        :param solicitacao: Solicitacao de serviço digital que será executada, neste caso cria um agendamento de visita e usuarios do AD
        :return: HttpResponse com informação sobre execução (Sucesso, Erro)
        """
        title = 'Solicitação de Visita a Campus/Unidade'
        solicitacao_etapa_1 = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=1)
        etapa_1 = Etapa.load_from_json(solicitacao_etapa_1.get_dados_as_json())

        solicitacao_etapa_2 = SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=2)
        etapa_2 = Etapa.load_from_json(solicitacao_etapa_2.get_dados_as_json())

        cpf_solicitante = etapa_1.formulario.get_value('cpf')
        visita_grupo = etapa_1.formulario.get_value('visita_grupo')
        data_saida = etapa_2.formulario.get_value('data_saida')
        data_entrada = etapa_2.formulario.get_value('data_entrada')
        objetivo = etapa_2.formulario.get_value('objetivo')
        campus = etapa_2.formulario.get_value('campus')
        arquivo_lista = self._obter_arquivo_lista(etapa_2, solicitacao)
        df = self._montar_df_visitantes(arquivo_lista, etapa_1)
        cpfs = df['CPF'].dropna().astype(str)
        initial = {
            'data': datetime.strptime(data_entrada, '%Y-%m-%d'),
            'data_saida': datetime.strptime(data_saida, '%Y-%m-%d'),
            'hora_entrada': time(8, 0),
            'hora_saida': time(18, 0),
            'atividade': objetivo,
        }

        form = SolicitacaoEntradaBalcaoDigitalForm(request.POST or None, request=request, initial=initial, campus=campus)
        if form.is_valid():
            try:
                # Cria os usuários externos
                with atomic(f'solicitar_visita_lock:{solicitacao.pk}', timeout=60):
                    # cadastra os usuários externos e usuários do AD
                    try:
                        for _index, row in df.iterrows():
                            self._cadastrar_visitante(row, bool(etapa_2.formulario.get_value('criar_usuario_ad')), data_saida)
                    finally:
                        self._fechar_arquivo_lista(arquivo_lista)

                # Cadastra a solicitação de visita
                solicitacao_visita = form.save()
                solicitacao_visita.deferido = True
                solicitacao_visita.solicitantes.set(Vinculo.objects.filter(user__username__in=cpfs).values_list('id', flat=True))
                solicitacao_visita.save()

                solicitacao.add_dado_registro_execucao(model_object=solicitacao_visita, operation='CREATE')
                solicitacao.status = Solicitacao.STATUS_ATENDIDO
                solicitacao.status_detalhamento = f"""A solicitação de entrada número {solicitacao_visita.id} foi criada com sucesso. <a href="{settings.SITE_URL}/portaria/solicitacao_entrada/{solicitacao_visita.id}/">Visualizar a solicitação.</a>"""
                solicitacao.save()
                # Registra acompanhamento e indica conclusão do serviço junto ao GOVBR
                self.registrar_acompanhamento(solicitacao)

                # Enviando o e-mail com a notificação de serviço atendido com sucesso.
                self.obter_formulario_avaliacao(solicitacao)
                dados_email = self.get_dados_email(solicitacao=solicitacao)
                url_avaliacao = None
                if solicitacao.get_registroavaliacao_govbr():
                    url_avaliacao = solicitacao.get_registroavaliacao_govbr().url_avaliacao

                mensagem_principal = f"""A solicitação de entrada número {solicitacao_visita.id} foi criada com sucesso. <a href="{settings.SITE_URL}/portaria/solicitacao_entrada/{solicitacao_visita.id}/">Visualizar a solicitação.</a>"""
                Notificar.notifica_conclusao_servico_atendido(
                    solicitacao, dados_email=dados_email, mensagem=mensagem_principal, url_avaliacao=url_avaliacao
                )
                self.registrar_conclusao(solicitacao)

                return httprr(
                    '/admin/catalogo_provedor_servico/solicitacao/',
                    mark_safe(f'A solicitação foi atendida através da criação da solicitação de visita número {solicitacao_visita.id}</a>.'),
                    tag='success',
                )
            except LockError:
                return httprr('/admin/catalogo_provedor_servico/solicitacao/', 'A solicitação já está sendo processada.', tag='error')
            except ValidationError as e:
                return httprr('/admin/catalogo_provedor_servico/solicitacao/', f'Erro de validação. {e}', tag='error')

        return locals()
