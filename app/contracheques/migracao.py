import logging
from decimal import Decimal

from django.db.models import Q
from tqdm import tqdm

from comum.models import Ano, Configuracao, EstadoCivil, Pensionista, PessoaEndereco, PessoaTelefone
from contracheques.models import ContraCheque, Rubrica, TipoRubrica
from djtools.utils import format_telefone, normalizar_nome_proprio, strptime_or_default
from rh.models import Banco, CargoClasse, CargoEmprego, GrupoCargoEmprego, JornadaTrabalho, Servidor, ServidorOcorrencia, Setor, Situacao, Titulacao
from rh.utils import extrai_matricula

log = logging.getLogger(__name__)

CODIFICACAO_ARQUIVOS_IMPORTACAO = 'latin-1'


def formata_decimal(valor):
    """
    '12345' -> Decimal('123.45')
    """
    return Decimal(f'{valor[:-2]}.{valor[-2:]}')


def formata_decimal_tipo_4(valor):
    """
    Valores negativos vem no formato 'NNNNM' com N = algarismos e M = indicador de sinal negativo
    """
    return valor.isdigit() and formata_decimal(valor) or 'M' in valor and formata_decimal(valor[:-1]).copy_negate() or Decimal('0.0')


def importar_rubricas(arquivo):
    novas_rubricas = []

    # FIXME: Não seria o caso incluir isso num fixture?
    TipoRubrica.objects.get_or_create(codigo='1', nome='Rendimento')
    TipoRubrica.objects.get_or_create(codigo='2', nome='Desconto')
    TipoRubrica.objects.get_or_create(codigo='3', nome='Outros')

    for linha in arquivo:
        linha = str(linha, CODIFICACAO_ARQUIVOS_IMPORTACAO)
        excluido = linha[0] == '1'
        codigo = linha[1:6]
        nome = linha[6:46].strip()
        rubrica, created = Rubrica.objects.get_or_create(codigo=codigo)
        if created:
            novas_rubricas.append(rubrica)
        rubrica.nome = nome
        rubrica.excluido = excluido
        rubrica.save()
    return novas_rubricas


def importar_contracheque(arquivo, tipo):
    novos_contracheques = []
    contracheques_atualizados = []
    try:
        is_servidor = tipo == 'servidores'
        is_pensionista = tipo == 'pensionistas'
        SITUACAO_PENSIONISTA = Situacao.objects.get(nome_siape__icontains='pensionista', excluido=False)
        ids_situacao_estagiario = Situacao.objects.filter(nome__icontains='ESTAGI').values_list('id', flat=True)
        for linha in tqdm(arquivo.readlines(), desc='Importação Contracheques'):
            linha = linha.decode(CODIFICACAO_ARQUIVOS_IMPORTACAO)
            if is_servidor:
                tipo = linha[17]
                if tipo == '0':
                    """Registro mestre (header), Identifica o arquivo e o órgão processado."""
                    mes = int(linha[45:47])
                    ano, _ano_created = Ano.objects.get_or_create(ano=int(linha[47:51]))

                elif tipo == '1':
                    """Contém os dados Pessoais do Servidor."""
                    servidor = Servidor.objects.filter(matricula=extrai_matricula(linha[9:16]))
                    servidor = servidor and servidor[0] or None
                    if servidor:
                        cc, cc_created = (
                            ContraCheque.objects.ativos().fita_espelho().get_or_create(servidor=servidor, pensionista=None, mes=mes, ano=ano)
                        )
                        if cc_created:
                            novos_contracheques.append(cc)
                        else:
                            contracheques_atualizados.append(cc)
                        cc.contrachequerubrica_set.all().delete()

                elif tipo == '2' and servidor:
                    """Contém os dados Funcionais do Servidor."""
                    cc.servidor_situacao = Situacao.objects.get(codigo=linha[23:25])
                    codigo_jornada = linha[90:92]
                    if codigo_jornada != '00':
                        cc.servidor_jornada_trabalho = JornadaTrabalho.objects.get(codigo=linha[90:92])
                    if int(linha[119:125]):
                        codigo_cargo_emprego = linha[119:125]
                        codigo_grupo_cargo_emprego = codigo_cargo_emprego[:3]
                        grupo_cargo_emprego = GrupoCargoEmprego.objects.get_or_create(codigo=codigo_grupo_cargo_emprego)[0]
                        cc.servidor_cargo_emprego = CargoEmprego.objects.get_or_create(
                            codigo=codigo_cargo_emprego, grupo_cargo_emprego=grupo_cargo_emprego
                        )[0]
                        cc.servidor_cargo_classe = CargoClasse.objects.get_or_create(codigo=linha[125:126])[0]
                    cc.servidor_nivel_padrao = linha[126:129]
                    try:
                        cc.servidor_setor_lotacao = Setor.objects.siape().get(codigo=linha[221:230])
                    except Setor.DoesNotExist:
                        pass
                    try:
                        cc.servidor_setor_localizacao = Setor.objects.siape().get(codigo=linha[243:252]) or None
                    except Setor.DoesNotExist:
                        pass
                    # verificando a titulação do servidor via contracheque (fita espelho: https://wiki.dtic.ifpr.edu.br/lib/exe/fetch.php/sist_gov:manual_fita_espelho_servidor.pdf)
                    try:
                        cc.servidor_titulacao = Titulacao.objects.get(codigo=linha[164:166])
                    except Titulacao.DoesNotExist:
                        pass

                    # se for estagiário e nao tiver setor de lotacao, seta um igual ao setor de localizacao
                    # isso vai corrigir o relatório quando é filtrado apenas por estagiário
                    if cc.servidor_situacao.id in ids_situacao_estagiario and not cc.servidor_setor_lotacao:
                        cc.servidor_setor_lotacao = cc.servidor_setor_localizacao

                elif tipo == '3' and servidor:
                    """Contém os dados Financeiros do Servidor."""
                    rendimento_desconto = linha[20]
                    codigo_rubrica = linha[21:26]
                    sequencia = linha[26]
                    valor = linha[27:38]
                    prazo = linha[38:41]
                    beneficiario_nome = linha[67:107]
                    beneficiario_banco_codigo = linha[107:110]
                    beneficiario_banco = Banco.objects.filter(codigo=beneficiario_banco_codigo)
                    beneficiario_banco = beneficiario_banco and beneficiario_banco[0] or False
                    if not beneficiario_banco:
                        beneficiario_banco = Banco.objects.create(codigo=beneficiario_banco_codigo, nome='REALIZE UMA EXTRaCAO DE BANCOS')
                    beneficiario_agencia = linha[110:116]
                    beneficiario_ccor = linha[116:129]
                    cc.insere_contra_cheque_rubrica(
                        rendimento_desconto=rendimento_desconto,
                        codigo_rubrica=codigo_rubrica,
                        sequencia=sequencia,
                        valor=formata_decimal(valor),
                        prazo=prazo,
                        beneficiario_nome=beneficiario_nome,
                        beneficiario_banco=beneficiario_banco,
                        beneficiario_agencia=beneficiario_agencia,
                        beneficiario_ccor=beneficiario_ccor,
                    )

                elif tipo == '4' and servidor:
                    """Contém a totalização dos dados Financeiros do Servidor."""
                    bruto = formata_decimal_tipo_4(linha[20:32])
                    desconto = formata_decimal_tipo_4(linha[32:44])

                    # Vou calcular o liquido para saber por qual algarismo substituirei o M
                    v = linha[44:56]
                    if bruto and desconto:
                        ult_alg = str(bruto - desconto)[-1]
                    liquido = (
                        v.isdigit() and formata_decimal(v) or 'M' in v and formata_decimal(v.replace('M', ult_alg)).copy_negate() or Decimal('0.0')
                    )

                    cc.bruto = bruto
                    cc.desconto = desconto
                    cc.liquido = liquido
                    cc.save()

            elif is_pensionista:
                tipo = linha[24]
                """
                Houve uma mudança no layout em Novembro/2011 para a fita-espélho de pensionistas. O espaço que registra o
                código do grau de parentesco passou de comprimento 2 para 3, aumentando consecutivamente a largura total
                do arquivo de 462 para 463.
                """
                s = None
                novo_modelo = len(linha) == 463
                if tipo == '0':
                    mes = int(linha[56:58])
                    ano = Ano.objects.get_or_create(ano=linha[52:56])[0]
                elif tipo == '1':
                    instituidor_matricula = linha[9:16]
                    pensionista_matricula = linha[16:24]
                    instituidor_matricula = extrai_matricula(instituidor_matricula)
                    """
                    A matricula é única. Entretanto, o usuário pode tentar inserir o contracheque de servidor
                    que ainda não foi importado (por isso uso filter na query abaixo). A FITA ESPELHO poderia
                    importar esse servidor caso ele não exista, mas essa é uma sugestão de implementação para o futuro.
                    """
                    s = Servidor.objects.filter(matricula=instituidor_matricula)
                    s = s and s[0] or False

                # elif tipo == '2' and s: Nao possui nenhum dado relevante para o pensionista
                elif tipo == '3' and s:
                    # print '--%s' % pensionista_nome
                    p, created = Pensionista.get_or_create(matricula=pensionista_matricula)
                    p.nome = normalizar_nome_proprio(linha[27:72])
                    p.nascimento_data = strptime_or_default(linha[72:80], '%d%m%Y')
                    p.cpf = linha[80:91]
                    p.sexo = linha[91]
                    p.estado_civil = EstadoCivil.objects.get(codigo_siape=linha[92:93])
                    p.rg = linha[95:109]
                    p.rg_orgao = linha[109:114]
                    p.rg_data = strptime_or_default(linha[114:122], '%d%m%Y')
                    p.rg_uf = linha[122:124]
                    logradouro = ' '.join(linha[124:227].split())
                    #               Nao tenho como separar logradouro, numero e complemento. Alem disso, o municipio vem
                    #               desassociado do estado, entao  entao estou jogando esses valores em logradouro e estou setando os demais como none
                    p.pessoaendereco_set.all().delete()
                    PessoaEndereco.objects.create(pessoa=p, logradouro=logradouro, municipio=None)
                    p.pessoatelefone_set.all().delete()
                    #                telefone = PessoaTelefone.formatar_telefone(linha[229:231], linha[231:239])
                    telefone = format_telefone(linha[229:231], linha[231:239])
                    if telefone:
                        PessoaTelefone.objects.create(pessoa=p, numero=telefone)
                    #                Os titulo na fita vem com 13 caracteres ... estou descartando o primeiro assumindo que ele sempre com 0
                    p.titulo_numero = linha[239:252][1:]
                    p.nome_mae = normalizar_nome_proprio(linha[252:302].strip())
                    email = linha[302:352].strip().lower()
                    if not Configuracao.eh_email_institucional(email):
                        p.email_secundario = email

                elif tipo == '4' and s:
                    pensionista_banco_codigo = novo_modelo and linha[64:67] or linha[63:66]
                    pensionista_banco, created = Banco.objects.get_or_create(codigo=pensionista_banco_codigo)
                    if created:
                        pensionista_banco.nome = 'REALIZE UMA EXTRaCAO DE BANCOS'
                        pensionista_banco.save()
                    p.pagto_banco = pensionista_banco
                    p.pagto_agencia = novo_modelo and linha[67:73] or linha[66:72]
                    p.pagto_ccor = novo_modelo and linha[75:88] or linha[74:87]
                    p.data_inicio_pagto_beneficio = (
                        novo_modelo and strptime_or_default(linha[125:133], '%d%m%Y') or strptime_or_default(linha[124:132], '%d%m%Y')
                    )
                    # Pensionistas perdem o beneficio por dois motivos: O limite foi alcançado (por ex. o filho completou 21 anos
                    # ou o pensionista foi excluido: (por ex. a esposa faleceu))
                    p.data_fim_pagto_beneficio = (
                        novo_modelo
                        and (strptime_or_default(linha[133:141], '%d%m%Y') or strptime_or_default(linha[453:461], '%d%m%Y'))
                        or (strptime_or_default(linha[132:140], '%d%m%Y') or strptime_or_default(linha[452:460], '%d%m%Y'))
                    )
                    p.save()
                    if p.data_fim_pagto_beneficio:
                        if mes == p.data_fim_pagto_beneficio.month and ano.ano == p.data_fim_pagto_beneficio.year:
                            gerar_contra_cheque = True
                        else:
                            gerar_contra_cheque = False
                    else:
                        gerar_contra_cheque = True
                    if gerar_contra_cheque:
                        cc, cc_created = ContraCheque.objects.ativos().fita_espelho().get_or_create(servidor=s, pensionista=p, mes=mes, ano=ano)
                        cc.servidor_situacao = SITUACAO_PENSIONISTA
                        if cc_created:
                            novos_contracheques.append(cc)
                        else:
                            contracheques_atualizados.append(cc)
                        cc.contrachequerubrica_set.all().delete()
                #             Tipos 5 e 6 trazem dados financeiros do instituidor. Segundo Josenilson eles são meramente para fins de
                #             consulta e não valem para contabilizar gastos em relatórios, por exemplo. Então, não devem ser guardados
                #             em banco. O que vale realmente começa a partir do tipo 7

                elif tipo == '7' and s:
                    #                   ContraChequr().servidor_situacao inicialmente era utilizado como historico da situacao do servidor.
                    #                   Quando pensionista passou a possuir contra-cheque no SUAP, percebi que seria interessante guardar a
                    #                   situacao PENSIONISTA para fins de facilidades no admin.py. Talvez o melhor fosse que ContraCheque
                    #                   estivesse associado com uma Pessoa e sua Situacao e nao com um Servidor e (se existe) o seu Pensionista
                    if gerar_contra_cheque:
                        rendimento_desconto = linha[27]
                        codigo_rubrica = linha[28:33]
                        prazo = linha[33:36]
                        sequencia = linha[36]
                        valor = linha[37:48]
                        cc.insere_contra_cheque_rubrica(
                            rendimento_desconto=rendimento_desconto,
                            codigo_rubrica=codigo_rubrica,
                            sequencia=sequencia,
                            valor=formata_decimal(valor),
                            prazo=prazo,
                        )
                elif tipo == '8' and s:
                    if gerar_contra_cheque:
                        v = linha[27:38]
                        # Valores negativos vem no formato 'NNNNM' com N = algarismos e M = indicador de sinal negativo
                        bruto = v.isdigit() and formata_decimal(v) or 'M' in v and formata_decimal(v[:-1]).copy_negate() or Decimal('0.0')
                        v = linha[38:49]
                        desconto = v.isdigit() and formata_decimal(v) or 'M' in v and formata_decimal(v[:-1]).copy_negate() or Decimal('0.0')
                        v = linha[49:60]
                        # Vou calcular o liquido para saber por qual algarismo substituirei o M
                        if bruto and desconto:
                            ult_alg = str(bruto - desconto)[-1]
                        liquido = (
                            v.isdigit()
                            and formata_decimal(v)
                            or 'M' in v
                            and formata_decimal(v.replace('M', ult_alg)).copy_negate()
                            or Decimal('0.0')
                        )

                        # Encontrei matriculas na fita-espelho que nao possuem um servidor associado.
                        # Seria esse o caso de cedidos?
                        cc.bruto = bruto
                        cc.desconto = desconto
                        cc.liquido = liquido
                        cc.save()
        arquivo.close()

        return {'NOVOS': str(len(novos_contracheques)), 'ATUALIZADOS': str(len(contracheques_atualizados))}

    except Exception as e:
        raise Exception(str(e))

    finally:
        # verificando dentro dos contracheques novos os que não tem rubricas
        for novo_cc in tqdm(novos_contracheques, desc='Removendo contracheques sem rubricas'):
            if not novo_cc.contrachequerubrica_set.exists():
                novos_contracheques.remove(novo_cc)
                novo_cc.delete()

        # verificando se nos contracheques atualizadas existe algum sem rubricas
        for atualizado_cc in tqdm(contracheques_atualizados, desc='Removendo contracheques sem rubricas'):
            if not atualizado_cc.contrachequerubrica_set.exists():
                contracheques_atualizados.remove(atualizado_cc)
                atualizado_cc.delete()

        # apagando qualquer contracheque remanecente que não tenha rubricas
        log.info('>>> Removendo contracheques sem rubricas.')
        ContraCheque.objects.filter(contrachequerubrica__isnull=True).delete()

        # verifica se existe contracheques cadastrado para servidores que ja foram excluidos
        # por exemplo: um estagiário que teve seu vículo encerrado na data 01/01/2022 não pode ter contracheque no mês 02
        # caso isso aconteça, esses contracheques são marcados como excluídos
        #
        # existem casos onde mesmo o servidor tendo uma ocorrência de exclusão, ainda é para ser mostrado o contracheques
        # é o caso de aposentados e instituidores de pensão
        log.info('>>> Verificando contracheques de servidores com ocorrência de exclusão.')
        for i in ServidorOcorrencia.objects.filter(servidor__ativo=False, ocorrencia__grupo_ocorrencia__nome='EXCLUSAO'):
            mes = i.data.month
            ano = i.data.year
            servidor = i.servidor
            qs = (
                ContraCheque.objects.filter(Q(ano__ano__gt=ano) | Q(ano__ano=ano, mes__gt=mes))
                .filter(servidor=servidor)
                .exclude(servidor__situacao__codigo__in=[Situacao.APOSENTADOS, Situacao.INSTITUIDOR_PENSAO, Situacao.PENSIONISTA])
            )
            if qs.exists():
                qs.update(excluido=True)
