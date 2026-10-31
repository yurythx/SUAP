import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from requests.exceptions import ConnectionError, ConnectTimeout, ReadTimeout, RetryError
from sentry_sdk import capture_exception

from djtools.db import models
from djtools.utils import get_datetime_now


class PessoaInfoComplementar(models.ModelPlus):
    """
    Classe que gerencia informações complementares de Pessoas obtidas por APIs disponibilizadas pelo Governo Federal
    """

    pessoa = models.ForeignKeyPlus('rh.Pessoa', verbose_name='Pessoa', on_delete=models.CASCADE)
    api_origem = models.ForeignKeyPlus('comum.APIExterna', verbose_name='API de Origem', on_delete=models.CASCADE)
    data_hora_consulta = models.DateTimeFieldPlus(auto_now_add=True)
    usuario = models.ForeignKeyPlus('comum.User', verbose_name='Usuario', null=True)
    informacoes = models.JSONField()

    class Meta:
        verbose_name = 'Informação Complementar de Pessoa'
        verbose_name_plural = 'Informações Complementares de Pessoa'
        constraints = [models.UniqueConstraint(fields=['pessoa', 'api_origem'], name='unique_info_api_govbr')]

    @staticmethod
    def obter_informacoes(api_origem, pessoa):
        from comum.models import APIExterna

        try:
            sucesso, resposta = False, []
            if pessoa.eh_pessoa_fisica:
                if not api_origem.ativo:
                    return False, ['API de consulta inativa.']
                cpf = pessoa.pessoafisica.cpf
                if not cpf:
                    return False, ['CPF não informado para pessoa física.']
                cpf = cpf.replace('.', '').replace('-', '').strip()
                if len(cpf) != 11:
                    return False, ['CPF deve ter 11 caracteres.']
                from comum.models import APIExterna

                if api_origem.nome in [APIExterna.SIAPE_NET.nome, APIExterna.SIAPE_CONECTA.nome]:
                    from rh.importador_ws import ImportadorWs

                    try:
                        resposta = ImportadorWs(api_origem).get_dados_pessoais(cpf)
                        sucesso = bool(resposta)
                    except Exception as e:
                        if settings.DEBUG:
                            raise e
                        sucesso, resposta = False, []
                else:
                    sucesso, resposta = api_origem.get_service().get_dados_pessoais(cpf)
            elif pessoa.eh_pessoa_juridica:
                api_origem = APIExterna.CNPJ
                if not api_origem.ativo:
                    return False, ['API de consulta inativa.']
                cnpj = pessoa.pessoajuridica.cnpj
                if not cnpj:
                    return False, ['CNPJ não informado para pessoa jurídica.']
                cnpj = cnpj.replace('.', '').replace('/', '').replace('-', '').strip()
                if len(cnpj) != 14:
                    return False, ['CNPJ deve ter 14 caracteres.']
                sucesso, resposta = api_origem.get_service().consulta_empresa(cnpj)
            return sucesso, resposta
        except (ConnectionError, ReadTimeout, ConnectTimeout, TypeError, RetryError, ValidationError) as e:
            if settings.DEBUG:
                raise e
            return False, ['Erro de conexão ao consultar a API. Tente novamente mais tarde.']
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)

    @staticmethod
    def atualizar_informacoes(pessoa, api_origem, usuario_consulta=None):
        try:
            sucesso, resposta = PessoaInfoComplementar.obter_informacoes(api_origem, pessoa)
            if sucesso:
                hoje = get_datetime_now()
                defaults = {'api_origem': api_origem, 'informacoes': resposta, 'data_hora_consulta': hoje}
                if usuario_consulta is not None:
                    defaults['usuario'] = usuario_consulta
                PessoaInfoComplementar.objects.update_or_create(pessoa=pessoa, api_origem=api_origem, defaults=defaults)
        except TypeError:
            pass
        except ValidationError:
            pass
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)

    @classmethod
    def get_instance(cls, pessoa, api_origem, usuario_consulta=None, force=False):
        """
        force = True deve ser utilizado para consumir informações da API
        force = False retorna informações da base de dados se existir
        """
        try:
            obj = cls.objects.get(pessoa=pessoa, api_origem=api_origem)
            if obj:
                if force:
                    cls.atualizar_informacoes(pessoa, api_origem, usuario_consulta=usuario_consulta)
                informacoes_consideradas_expiradas = datetime.datetime.today() > (
                    obj.data_hora_consulta + datetime.timedelta(days=api_origem.dias_para_expirar)
                )
                if informacoes_consideradas_expiradas:
                    cls.atualizar_informacoes(pessoa, api_origem, usuario_consulta=usuario_consulta)
                return obj
        except cls.DoesNotExist:
            cls.atualizar_informacoes(pessoa, api_origem, usuario_consulta=usuario_consulta)
            if obj := cls.objects.filter(pessoa=pessoa, api_origem=api_origem).first():
                return obj
        except cls.MultipleObjectsReturned:
            # Remove os registros mais antigos e mantém somente o atual que é retornado
            ultimo_id = cls.objects.filter(pessoa=pessoa, api_origem=api_origem).order_by('-data_hora_consulta').values_list('id', flat=True).first()

            # Se encontrou um ID válido, exclui os outros registros duplicados
            if ultimo_id:
                cls.objects.filter(pessoa=pessoa, api_origem__nome=api_origem).exclude(pk=ultimo_id).delete()
                return cls.objects.get(pk=ultimo_id)
