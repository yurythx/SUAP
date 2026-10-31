import re
from datetime import datetime
from typing import cast

from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from comum.models import Ano
from djtools.utils import cpf_valido, mask_cpf


def extrair_ano(data):
    if data:
        ano = data.year
        try:
            return Ano.objects.get(ano=ano)
        except ObjectDoesNotExist:
            raise ValueError(f'Nenhum objeto Ano correspondente a {ano} foi encontrado.')


def extrair_periodo_letivo(data_inicio):
    mes = data_inicio.month
    # Retorna 1 se o mês estiver entre janeiro e junho (inclusive), caso contrário retorna 2
    return 1 if mes <= 6 else 2


def handle_error(mensagem_erro, lista_erro, raise_exception):
    """
    Handle errors by either appending to a list or raising an exception based on the flag.
    """
    if raise_exception:
        raise ValueError(mensagem_erro)
    if lista_erro is not None:
        lista_erro.append(mensagem_erro)


def validar_formatacao_cpf(
    valor: str | None, nome_campo: str, obrigatorio: bool = True, erros: list[str] | None = None, raise_exception: bool = False
) -> str | None:
    """
    Valida um CPF: exige 11 dígitos (a pontuação é ignorada) e dígito verificador válido.

    :param valor: O valor do campo a ser validado.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param obrigatorio: Se o campo é obrigatório. Padrão é True.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: O CPF no formato canônico "000.000.000-00" (o gravado em ``PessoaFisica.cpf``),
        '' se opcional e vazio, ou None se ocorreu um erro e a exceção não foi levantada.
    """
    valor = valor.strip() if isinstance(valor, str) and valor else valor

    if not valor:
        if not obrigatorio:
            return ''
        # Campo obrigatório e vazio
        erro = f'O campo {nome_campo} é obrigatório e não pode estar vazio. Valor fornecido: "{valor}".'
        return handle_error(erro, erros, raise_exception)

    # Verifica se o valor atende às condições de formatação
    cpf_puro = re.sub(r'\D', '', valor)  # Remove todos os caracteres não numéricos

    if len(cpf_puro) != 11:
        erro = f'O campo {nome_campo} deve conter exatamente 11 dígitos. Valor fornecido: "{valor}".'
        return handle_error(erro, erros, raise_exception)

    cpf = mask_cpf(cpf_puro, clean=False)
    # Pontuação não é recusada (#17410); DV inválido e sequência repetida são (cpf_valido).
    if not cpf_valido(cpf):
        erro = f'O campo {nome_campo} contém um CPF inválido (dígito verificador não confere). Valor fornecido: "{valor}".'
        return handle_error(erro, erros, raise_exception)

    return cpf


def validar_passaporte(
    valor: str | None, nome_campo: str, obrigatorio: bool = True, erros: list[str] | None = None, ignorar_obrigatorios: bool = False
) -> str | None:
    """Como ``validar_string``, mas recusa o passaporte que a higiene anularia (menos de 5 caracteres, um caractere repetido ou sem dígito)."""
    from rh.deduplicacao.documentos import passaporte_valido

    passaporte = validar_string(valor, nome_campo, obrigatorio=obrigatorio, erros=erros, ignorar_obrigatorios=ignorar_obrigatorios)
    if passaporte and not passaporte_valido(passaporte):
        return handle_error(f'O campo {nome_campo} contém um passaporte inválido. Valor fornecido: "{passaporte}".', erros, False)
    return passaporte


def validar_string(valor, nome_campo, obrigatorio=True, max_len=None, erros=None, raise_exception=False, ignorar_obrigatorios=False):
    """
    Valida se o valor é uma string, considerando se é um campo obrigatório e verificando o comprimento máximo.

    :param valor: O valor do campo a ser validado.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param obrigatorio: Se o campo é obrigatório. Padrão é True.
    :param max_len: O comprimento máximo permitido para a string. Padrão é None, sem limite.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: O valor validado ou ajustado (como uma string limpa), ou None se ocorreu um erro e a exceção não foi levantada.
    """
    # Se ignorar_obrigatorios estiver True, ignorar a obrigatoriedade do campo
    if ignorar_obrigatorios:
        obrigatorio = False

    valor = valor.strip() if isinstance(valor, str) and valor else valor

    if obrigatorio and not valor:
        erro = f'O campo {nome_campo} é obrigatório e não pode estar vazio.'
        return handle_error(erro, erros, raise_exception)

    if valor and max_len is not None and len(valor) > max_len:
        erro = f'O campo {nome_campo} excede o comprimento máximo de {max_len} caracteres.'
        return handle_error(erro, erros, raise_exception)

    return valor


def validar_inteiro(
    valor: str | int | None,
    min_val: int | None = None,
    max_val: int | None = None,
    nome_campo: str = '',
    obrigatorio: bool = True,
    erros: list[str] | None = None,
    raise_exception: bool = False,
    ignorar_obrigatorios: bool = False,
) -> int | None:
    """
    Valida se o valor é um inteiro e opcionalmente se está dentro de um intervalo.

    :param valor: O valor do campo a ser validado.
    :param min_val: O valor mínimo permitido.
    :param max_val: O valor máximo permitido.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param obrigatorio: Indica se o campo é obrigatório.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: O valor inteiro validado ou None.
    """
    # Se ignorar_obrigatorios estiver True, ignorar a obrigatoriedade do campo
    if ignorar_obrigatorios:
        obrigatorio = False

    valor = valor.strip() if isinstance(valor, str) and valor else valor

    # Vazio é só None/'' (após o strip): `not valor` recusaria o zero legítimo (#17411).
    if valor is None or valor == '':
        if obrigatorio:
            erro = f'O campo {nome_campo} é obrigatório e não pode estar vazio.'
            return handle_error(erro, erros, raise_exception)
        return None

    # O try cobre só a conversão: o ValueError de handle_error não pode ser recapturado (#17409).
    try:
        valor_int = int(valor)
    except TypeError, ValueError:
        erro = f'O campo {nome_campo} requer um valor inteiro válido. "{valor}" foi informado.'
        return handle_error(erro, erros, raise_exception)
    if (min_val is not None and valor_int < min_val) or (max_val is not None and valor_int > max_val):
        erro = f'O campo {nome_campo} deve estar entre {min_val} e {max_val}.'
        return handle_error(erro, erros, raise_exception)
    return valor_int


def validar_decimal(
    valor: str | float | None,
    min_val: float | None = None,
    max_val: float | None = None,
    nome_campo: str = '',
    obrigatorio: bool = True,
    erros: list[str] | None = None,
    raise_exception: bool = False,
    ignorar_obrigatorios: bool = False,
) -> float | None:
    """
    Valida se o valor é um decimal e opcionalmente se está dentro de um intervalo.

    :param valor: O valor do campo a ser validado.
    :param min_val: O valor mínimo permitido.
    :param max_val: O valor máximo permitido.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param obrigatorio: Indica se o campo é obrigatório.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: O valor decimal validado ou None.
    """
    # Se ignorar_obrigatorios estiver True, ignorar a obrigatoriedade do campo
    if ignorar_obrigatorios:
        obrigatorio = False

    valor = valor.strip() if isinstance(valor, str) and valor else valor

    # Vazio é só None/'' (após o strip): `not valor` recusaria o zero legítimo (#17411).
    if valor is None or valor == '':
        if obrigatorio:
            erro = f'O campo {nome_campo} é obrigatório e não pode estar vazio.'
            return handle_error(erro, erros, raise_exception)
        return None

    # O try cobre só a conversão: o ValueError de handle_error não pode ser recapturado (#17409).
    try:
        valor_decimal = float(valor)
    except TypeError, ValueError:
        erro = f'O campo {nome_campo} requer um valor decimal válido. "{valor}" foi informado.'
        return handle_error(erro, erros, raise_exception)
    if (min_val is not None and valor_decimal < min_val) or (max_val is not None and valor_decimal > max_val):
        erro = f'O campo {nome_campo} deve estar entre {min_val} e {max_val}.'
        return handle_error(erro, erros, raise_exception)
    return valor_decimal


def validar_data(valor, nome_campo='', erros=None, raise_exception=False):
    """
    Valida se o valor é uma data no formato dd/mm/yyyy.

    :param valor: O valor do campo a ser validado.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: Objeto date correspondente ao valor, se válido.
    """
    if valor == '':
        return None  # Ou retornar um valor padrão se aplicável

    try:
        return datetime.strptime(valor, '%d/%m/%Y').date()
    except Exception:
        erro = f'O campo {nome_campo} requer uma data válida no formato dd/mm/yyyy.'
        return handle_error(erro, erros, raise_exception)


def validar_booleano(valor: object, nome_campo: str = '', erros: list[str] | None = None, raise_exception: bool = False) -> bool | None:
    """
    Converte valores conhecidos para booleano (1, Sim, 0, Não, True, False) ou levanta erro.

    :param valor: O valor do campo a ser validado.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: Booleano correspondente ao valor, se válido.
    """
    if valor is None or valor == '':
        return None  # Ou considerar False como padrão para campos booleanos vazios

    # str() antes do lower(): True/1 viram 'true'/'1'; outro tipo cai na mensagem, não em AttributeError (#17411).
    valor_lower = str(valor).lower()
    if valor_lower in ['1', 'sim', 'true']:
        return True
    elif valor_lower in ['0', 'não', 'nao', 'false']:
        return False
    else:
        erro = f'O campo {nome_campo} requer um valor booleano (1, Sim, 0, Não, True, False).'
        return handle_error(erro, erros, raise_exception)


def validar_modelo(
    valor: str | int | None,
    modelo: type[models.Model],
    nome_campo: str,
    campo_modelo: str = 'id',
    forcar_criacao: bool = False,
    obrigatorio: bool = True,
    erros: list[str] | None = None,
    raise_exception: bool = False,
    ignorar_obrigatorios: bool = False,
) -> int | None:
    """
    Valida se o valor corresponde a um registro válido no modelo dado, baseado em um campo específico do modelo.
    O método pode levantar uma exceção diretamente ou acumular erros em uma lista, dependendo dos parâmetros.
    A consulta é realizada de maneira case-insensitive para campos de texto.

    :param valor: O valor do campo a ser validado.
    :param modelo: O modelo Django no qual buscar o registro correspondente.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param campo_modelo: O nome do campo no modelo a ser utilizado para a busca. Padrão é 'id'.
    :param forcar_criacao: Se True, cria um novo registro no modelo caso não exista. Padrão é False.
    :param obrigatorio: Indica se o campo é obrigatório.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :param ignorar_obrigatorios: Se True, ignora a verificação de obrigatoriedade do campo.
    :return: O objeto do modelo correspondente ao valor, se encontrado.
    """
    if ignorar_obrigatorios:
        obrigatorio = False

    # Normaliza o tipo na entrada: pk int vira a string equivalente, None vira vazio (#17411).
    valor = '' if valor is None else str(valor)

    if obrigatorio and not valor:
        erro = f'O campo {nome_campo} é obrigatório e não pode estar vazio.'
        return handle_error(erro, erros, raise_exception)

    if valor in ['', '0']:
        return None

    filtro = _filtro_validar_modelo(valor, modelo, campo_modelo)

    # O try cobre só a consulta: o ValueError de handle_error não pode ser recapturado pelo
    # except Exception, que trocaria a mensagem específica pela genérica (#17409).
    try:
        objeto = modelo.objects.filter(**filtro).order_by('id').only('id').first()
    except modelo.MultipleObjectsReturned:
        erro = f'Múltiplos registros encontrados para o campo {nome_campo} com {campo_modelo} "{valor}".'
        return handle_error(erro, erros, raise_exception)
    except Exception:
        erro = f'O campo {nome_campo} requer um valor válido para {campo_modelo}. "{valor}" foi informado.'
        return handle_error(erro, erros, raise_exception)

    if objeto:
        return objeto.pk
    erro = f'O campo {nome_campo} com {campo_modelo} "{valor}" não foi encontrado.'
    if forcar_criacao:
        try:
            objeto = modelo.objects.create(**{campo_modelo: valor.strip()})
            return objeto.pk
        except Exception:
            erro = f'Erro ao tentar criar o objeto {campo_modelo} com o campo {nome_campo} igual a {valor}.'
    return handle_error(erro, erros, raise_exception)


def _filtro_validar_modelo(valor: str, modelo: type[models.Model], campo_modelo: str) -> dict[str, str]:
    """Monta o filtro de busca de ``validar_modelo``, case-insensitive quando o campo final é texto."""
    # Obter o campo do modelo para verificar o tipo
    campos = campo_modelo.split('__')
    modelo_temp = modelo
    campo_final = None
    for campo_temp in campos:
        if campo_temp == campos[-1]:
            campo_final = modelo_temp._meta.get_field(campo_temp)
        else:
            modelo_temp = cast(type[models.Model], modelo_temp._meta.get_field(campo_temp).related_model)

    if campo_final and isinstance(campo_final, models.CharField | models.TextField):
        return {f'{campo_modelo}__iexact': valor.strip()}
    return {campo_modelo: valor.strip()}
