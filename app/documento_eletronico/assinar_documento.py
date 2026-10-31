from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from djtools.security.signature import create_signature
from djtools.utils import get_datetime_now

if TYPE_CHECKING:
    from comum.models import User
    from rh.models import Papel

    from documento_eletronico.models import DocumentoTexto


def get_chave_secreta():
    return settings.DOC_SECRET_KEY


def get_chave(secret):
    return f'{get_chave_secreta()}:{secret}'


def gerar_assinatura_documento_senha(documento, vinculo):
    chave = get_chave(vinculo.secret)
    # print (u'>>> ')
    # print (u'>>> ASSINATURA DO DOCUMENTO: {} ||| por {}'.format(documento, pessoa_fisica))
    # print (u'>>> >>> {}'.format(chave))
    # print (u'>>> >>> {}'.format(documento.hash_conteudo))
    # print (u'>>> ')

    return create_signature(chave, documento.hash_conteudo).decode('utf-8')


def verificar_assinatura_senha(documento, vinculo, assinatura_hmac):
    return gerar_assinatura_documento_senha(documento, vinculo) == assinatura_hmac


def assinar_documento_com_senha(documento: DocumentoTexto, user: User, papel: Papel) -> None:
    """Atribui o identificador definitivo a ``documento``, assina-o por senha e o finaliza.

    O gerador de identificador devolve a sigla do setor no último item da tupla para documentos
    de setor e o dono do documento para documentos pessoais (aqueles sem ``setor_dono``); o valor
    é encaminhado para o campo correspondente.

    Args:
        documento: documento de texto a ser identificado, assinado e finalizado.
        user: usuário que assina o documento com a própria senha.
        papel: papel institucional usado na assinatura.

    Raises:
        ValidationError: se o papel não puder assinar o tipo de documento ou se o usuário não
            puder assinar o documento.
    """
    data_emissao = get_datetime_now()
    # Gera a sugestao do identificador
    # ------------------------
    # Em documentos pessoais o último item da tupla é o dono do documento, e não a sigla do setor.
    identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla_ou_dono = (
        documento.get_sugestao_identificador_definitivo(tipo_documento_texto=documento.modelo.tipo_documento_texto, setor_dono=documento.setor_dono)
    )
    eh_documento_pessoal = documento.eh_documento_pessoal
    documento.atribuir_identificador_e_processar_conteudo_final(
        identificador_tipo_documento_sigla=identificador_tipo_documento_sigla,
        identificador_numero=identificador_numero,
        identificador_ano=identificador_ano,
        identificador_setor_sigla=None if eh_documento_pessoal else identificador_setor_sigla_ou_dono,
        identificador_dono_documento=identificador_setor_sigla_ou_dono if eh_documento_pessoal else None,
        data_emissao=data_emissao,
    )
    documento.assinar_via_senha(user, papel, data_emissao)
    documento.finalizar_documento()
    documento.save()
