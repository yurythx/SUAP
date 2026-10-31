"""Regras de documento de pessoa física: formatação, validade e documento sintético.

Fonte única usada pela higiene do comando ``deduplicar_pessoas`` e pela entrada de dados
(``PessoaFisica.save`` e ``PessoaFisica.objects.obter_ou_criar``).
"""

from __future__ import annotations

import re
import unicodedata

from django.core.exceptions import ValidationError
from pycpfcnpj import cpfcnpj

from djtools.utils.masks import PREFIXOS_SINTETICOS

# guardam a história (o documento separado, o CPF anulado) e nunca são recalculados; SEMDOC-/SEMPAIS- seguem a PF
PREFIXOS_HISTORICOS = ('CONFLITO-', 'INVALIDO-')
TAMANHO_MINIMO_PASSAPORTE = 5
# a chave ``ARG-AB123456`` é o login do estrangeiro sem CPF: ISO + hífen + número cabe nos 30 da matrícula do prestador
TAMANHO_MAXIMO_PASSAPORTE = 30 - len('ARG-')
MENSAGEM_PASSAPORTE_INVALIDO = (
    f'Passaporte inválido: informe o número, de {TAMANHO_MINIMO_PASSAPORTE} a {TAMANHO_MAXIMO_PASSAPORTE} letras e dígitos, com ao menos um dígito.'
)


def digitos(valor: str | None) -> str:
    return re.sub(r'\D', '', valor or '')


def formatar_cpf(valor: str | None) -> str | None:
    """Máscara ``000.000.000-00`` quando há 11 dígitos; ``None`` quando não há dígito nenhum.

    Só formata: um CPF com DV errado continua como está (anulá-lo é decisão auditada da higiene).
    """
    numeros = digitos(valor)
    if not numeros:
        return None
    if len(numeros) == 11:
        return f'{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}'
    return (valor or '').strip()


def cpf_valido(valor: str | None) -> bool:
    numeros = digitos(valor)
    return len(numeros) == 11 and len(set(numeros)) > 1 and cpfcnpj.validate(numeros)


def formatar_passaporte(valor: str | None) -> str | None:
    """Só letras e dígitos ASCII, em maiúsculas: o número vira login (``userPrincipalName``) na chave ``ARG-AB123456``.

    Tira a pontuação antes de pôr em maiúsculas (``'ß'.upper()`` é ``'SS'``).
    """
    return re.sub(r'[^A-Za-z0-9]', '', valor or '').upper() or None


def passaporte_valido(valor: str | None) -> bool:
    """Todo passaporte tem número: sem dígito é texto de recusa digitado no campo ("NÃO TENHO", "SEM PASSAPORTE"), que juntaria
    pessoas diferentes num mesmo documento (no suap_dev, 197 PFs). Acima do máximo, a chave não cabe no login."""
    passaporte = formatar_passaporte(valor)
    return (
        bool(passaporte)
        and TAMANHO_MINIMO_PASSAPORTE <= len(passaporte) <= TAMANHO_MAXIMO_PASSAPORTE
        and len(set(passaporte)) > 1
        and any(caractere.isdigit() for caractere in passaporte)
    )


def recusar_documento_invalido(cpf: str | None, passaporte: str | None) -> None:
    """PF nova: CPF inválido, ou passaporte inválido sem CPF, não é documento.

    A higiene anularia o documento e a próxima entrada, sem achar ninguém, criaria outra PF (loop de duplicata).
    """
    if cpf and not cpf_valido(cpf):
        raise ValidationError('CPF inválido.')
    if not cpf and passaporte and not passaporte_valido(passaporte):
        raise ValidationError(MENSAGEM_PASSAPORTE_INVALIDO)


MENSAGEM_PAIS_SEM_ISO = 'País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países.'


def recusar_pais_sem_iso(cpf: str | None, passaporte: str | None, tem_pais: bool, iso_alfa3: str | None) -> None:
    """PF nova sem CPF: passaporte válido com país sem ISO 3166-1 alfa-3 não forma documento (a legada recebe sintético na higiene)."""
    if not cpf and passaporte_valido(passaporte) and tem_pais and not iso_alfa3:
        raise ValidationError(MENSAGEM_PAIS_SEM_ISO)


def eh_sintetico(documento: str | None) -> bool:
    return (documento or '').startswith(PREFIXOS_SINTETICOS)


def documento_sintetico(pf_id: int, conflito: str | None = None, cpf_invalido: str | None = None, passaporte_sem_pais: str | None = None) -> str:
    """Documento da PF sem chave. ``SEMPAIS-<id>-<passaporte>``: passaporte válido sem país (não forma chave, mas fica buscável)."""
    if conflito:
        return f'CONFLITO-{pf_id}-{conflito}'
    if digitos(cpf_invalido):
        return f'INVALIDO-{pf_id}-{digitos(cpf_invalido)}'
    if passaporte_valido(passaporte_sem_pais):
        return f'SEMPAIS-{pf_id}-{formatar_passaporte(passaporte_sem_pais)}'
    return f'SEMDOC-{pf_id}'


def documento_original(documento: str | None) -> str | None:
    """O documento separado dentro de ``CONFLITO-<id>-<documento>``; qualquer outro volta como está."""
    if (documento or '').startswith('CONFLITO-'):
        return documento.split('-', 2)[2]
    return documento


def sintetico_atual(pf_id: int, documento: str | None, passaporte: str | None, tem_pais: bool) -> str:
    """O sintético da PF sem chave: o histórico (``CONFLITO-``/``INVALIDO-``) fica; ``SEMDOC-``/``SEMPAIS-`` seguem o passaporte atual."""
    if (documento or '').startswith(PREFIXOS_HISTORICOS):
        return documento
    return documento_sintetico(pf_id, passaporte_sem_pais=None if tem_pais else passaporte)


def chave_passaporte(passaporte: str | None, iso_alfa3: str | None) -> str | None:
    """Passaporte só identifica junto com o ISO 3166-1 alfa-3 do país emissor: ``ARG-AB123456``. Sem ele, não é documento.

    É também o login do estrangeiro sem CPF, por isso só letras, dígitos e hífen (cabe em ``userPrincipalName``).
    """
    passaporte = formatar_passaporte(passaporte)
    return f'{iso_alfa3}-{passaporte}' if passaporte and iso_alfa3 else None


def normalizar_nome_pais(nome: str | None) -> str:
    sem_acento = unicodedata.normalize('NFKD', nome or '').encode('ascii', 'ignore').decode()
    return sem_acento.upper().strip()
