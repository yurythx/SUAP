from djtools.utils import get_datetime_now


def montar_identificador_sigla(setor_dono):
    # Montagem da Sigla de Documento
    setor_arvore_completa = setor_dono.get_caminho(ordem_descendente=False)
    # Os setores colegiados estão subordinados a RE, mas RE não deve aparecer no nome do documento.
    if setor_dono.eh_orgao_colegiado:
        setor_arvore_completa.remove(setor_dono.superior)
    #
    # Rotina antiga
    # identificador_setor_sigla = '/'.join(str(s) for s in setor_arvore_completa)
    """
        A rotina antiga, por conta do cadastro da sigla da forma que está, incluindo a sigla do campus ('SetorX/CampusY),
        está gerando identificadores muito grandes. Como não é possível ajustar os cadastros pare remover essa informação,
        por conta de outros sistemas, então fizemos uma rotina que suprime a "sigla do campus" que estiver presente dentro
        da "sigla do setor". Abaixo um exemplo de como era e como ficou:

        Setor Coordenação de Licenciatura em Espanhol
        Sigla: CLIESP/CNAT
        Sigla da Árvore Completa: CLIESP/CNAT/COESUP/CNAT/DIAC/CNAT/DG/CNAT/RE/IFRN (tamanho: 49)
        Sigla da Árvore Completa Simplificada: CLIESP/COESUP/DIAC/DG/CNAT/RE/IFRN (tamanho: 34)
        Setor é campus: Não

        Setor Coordenação de Finanças, Material e Patrimônio do Campus Avançado Lajes
        Sigla: COFIMPAT/LAJ
        Sigla da Árvore Completa: COFIMPAT/LAJ/DIAD/LAJ/DG/LAJ/DG/JC/RE/IFRN (tamanho: 42)
        Sigla da Árvore Completa Simplificada: COFIMPAT/DIAD/DG/LAJ/DG/JC/RE/IFRN (tamanho: 34)
        Setor é campus: Não

        Setor Direção Geral de Lajes
        Sigla: DG/LAJ
        Sigla da Árvore Completa: DG/LAJ/DG/JC/RE/IFRN (tamanho: 20)
        Sigla da Árvore Completa Simplificada: DG/LAJ/DG/JC/RE/IFRN (tamanho: 20)
        Setor é campus: Sim (LAJ)
    """
    # Rotina nova
    identificador_setor_sigla = ''
    for setor in setor_arvore_completa:
        if not setor.uo or setor.setor_eh_campus:
            identificador_setor_sigla = identificador_setor_sigla + setor.sigla + '/'
        else:
            identificador_setor_sigla = identificador_setor_sigla + setor.sigla.replace('/' + setor.uo.sigla, '') + '/'
    #
    identificador_setor_sigla = identificador_setor_sigla[:-1]
    return identificador_setor_sigla


def identificador_sequencial(klass, tipo_documento_texto, setor_dono, identificador_ano=None, **kwargs):
    #
    identificador_tipo_documento_sigla = tipo_documento_texto.sigla
    identificador_setor_sigla = montar_identificador_sigla(setor_dono)
    filters = {
        'modelo__tipo_documento_texto': tipo_documento_texto,
        'setor_dono': setor_dono,
    }
    if identificador_ano:
        filters.update({'identificador_ano': identificador_ano})
    #
    ultimo_id = klass.get_ultimo_identificador_definitivo(**filters)
    identificador_numero = ultimo_id + 1
    identificador_ano = identificador_ano or get_datetime_now().year
    return identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla


def identificador_sequencial_anual_impessoal(klass, tipo_documento_texto, setor_dono):
    ano = get_datetime_now().year
    identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla = identificador_sequencial(
        klass, tipo_documento_texto, setor_dono, ano
    )
    return identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla


def identificador_sequencial_pessoal(klass, tipo_documento_texto, usuario, documento_id):
    # Devido a solitações nas demandas 1078 e 1068 o padrão passou
    # De: Acordo 1/2021 - Servidor/1931743
    # Para: Acordo 1/2021 - Servidor/[Nome usual]/193****
    # identificador_tipo_documento_sigla
    identificador_tipo_documento_sigla = tipo_documento_texto.sigla
    # identificador_ano
    identificador_ano = get_datetime_now().year
    # identificador_numero
    ultimo_documento_pessoa = klass.get_ultimo_identificador_definitivo(
        tipo_documento_texto, usuario_criacao=usuario, identificador_ano=identificador_ano
    )
    identificador_numero = ultimo_documento_pessoa + 1

    # A anonimização será tratada por demanda específica
    # Assim, tiramos do identificador a matrícula (aluno e servidor) e o CPF
    # Não fará mais parte do das demandas 1068 e 1078
    """
        username_anonim = None
        if sigla_vinculo(usuario) == 'Prestador de Serviço':
            username_anonim = anonimizar_cpf(usuario.username)
        elif sigla_vinculo(usuario) == 'Aluno':
            username_anonim = anonimizar_identificador_unico_matricula_aluno(usuario.username)
        else:
            username_anonim = anonimizar_identificador_unico_matricula_servidor(usuario.username)
        identificador_dono_documento = '{}/{}/{}'.format(sigla_vinculo(usuario), usuario.get_profile().nome_usual, username_anonim)
    """
    sigla_vinculo = usuario.get_vinculo().get_vinculo_institucional_title
    identificador_dono_documento = f'{sigla_vinculo}/{usuario.get_profile().nome_usual}/{documento_id}'
    # Identificador
    return identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_dono_documento


def identificador_sequencial_anual(pessoal, **kwargs):
    return identificador_sequencial_anual_impessoal(**kwargs) if not pessoal else identificador_sequencial_pessoal(**kwargs)
