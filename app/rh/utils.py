import os
import re
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.conf import settings
from django.contrib.admin import SimpleListFilter
from django.db.models import Model
from django.utils.translation import gettext_lazy as _

from djtools.utils import int_to_roman

# IFMA - Daniel Lima
MOTIVO_FERIAS = 'ferias'
MOTIVO_LICENCA_CAPACITACAO = 'licenca_capacitacao'
MOTIVO_LICENCA_MEDICA = 'licenca_medica'
MOTIVO_RECESSO_NATALINO = 'recesso_natalino'
MOTIVO_VIAGEM = 'viagem'
MOTIVO_OUTROS = 'outros'
TIPOS_SUBSTITUICAO_CHOICE = (
    (MOTIVO_FERIAS, 'Férias'),
    (MOTIVO_LICENCA_CAPACITACAO, 'Licença Capacitação'),
    (MOTIVO_LICENCA_MEDICA, 'Licença Médica'),
    (MOTIVO_RECESSO_NATALINO, 'Recesso Natalino'),
    (MOTIVO_VIAGEM, 'Viagem'),
    (MOTIVO_OUTROS, 'Outros'),
)


# IFMA/Tássio
def get_corpo_situacao_funcional(corpo, servidor, user, processo):
    corpo = corpo.replace('###NUM_PROCESSO###', processo.numero_processo)
    servidor_logado = user.get_relacionamento()
    if not servidor.eh_servidor_efetivo():
        corpo = corpo.replace('em caráter efetivo ', '').replace('efetivo ', '')
    corpo = corpo.replace('###NOME_DO_SERVIDOR###', servidor.pessoa_fisica.nome)
    corpo = corpo.replace('###MATRICULA_DO_SERVIDOR###', servidor.matricula)
    corpo = corpo.replace('###CARGO###', servidor.cargo_emprego.nome)
    corpo = corpo.replace('###CAMPUS_INGRESSO###', servidor.dadosextrasservidor.campus_ingresso.nome)
    corpo = corpo.replace('###PORTARIA_INGRESSO###', servidor.dadosextrasservidor.portaria_ingresso)
    corpo = corpo.replace('###DATA_PORTARIA_INGRESSO###', servidor.dadosextrasservidor.data_portaria_ingresso.strftime('%d/%m/%Y'))
    corpo = corpo.replace('###DATA_PORTARIA_INGRESSO_NO_DOU###', servidor.dadosextrasservidor.data_portaria_ingresso_no_dou.strftime('%d/%m/%Y'))
    corpo = corpo.replace('###CLASSE_LETRA###', servidor.cargo_classe.nome[-1:])
    corpo = corpo.replace('###CATEGORIA###', servidor.categoria_display.title())

    pca = servidor.pca_set.filter(cargo_pca=servidor.cargo_emprego).order_by('-data_entrada_pca').first()
    if hasattr(pca, 'jornadatrabalhopca_set'):
        jornada = pca.jornadatrabalhopca_set.all().order_by('data_inicio_jornada_trabalho_pca').first().qtde_jornada_trabalho_pca
        corpo = corpo.replace('###JORNADA_TRABALHO_INICIAL###', jornada)
    else:  # Teoricamente são servidores novos que ainda não mudaram jornada de trabalho, então = atual.
        corpo = corpo.replace('###JORNADA_TRABALHO_INICIAL###', servidor.jornada_trabalho.codigo)
    if '99 horas semanais' in corpo:
        corpo = corpo.replace('99 horas semanais de trabalho', '40 horas semanais de trabalho com Dedicação Exclusiva')

    # As duas informações abaixo vinham da classe Servidor e agora vem da classe DadosExtrasServidor
    corpo = corpo.replace('###DATA_POSSE###', servidor.dadosextrasservidor.data_posse_instituicao.strftime('%d/%m/%Y'))
    corpo = corpo.replace('###DATA_EXERCICIO###', servidor.dadosextrasservidor.data_inicio_exercicio_instituicao.strftime('%d/%m/%Y'))

    primeira_lotacao = servidor.servidorsetorlotacaohistorico_set.order_by('data_inicio_setor_lotacao').first()
    corpo = corpo.replace('###PORTARIA_LOTACAO###', primeira_lotacao.dadosextraslotacaoservidor.portaria)
    corpo = corpo.replace('###DATA_PORTARIA_LOTACAO###', primeira_lotacao.dadosextraslotacaoservidor.data_portaria.strftime('%d/%m/%Y'))
    corpo = corpo.replace('###CAMPUS_LOTACAO###', primeira_lotacao.dadosextraslotacaoservidor.campus_lotacao.nome)
    corpo = corpo.replace('###DATA_LOTACAO###', primeira_lotacao.data_inicio_setor_lotacao.strftime('%d/%m/%Y'))
    corpo = corpo.replace('###SETOR_INGRESSO###', servidor.dadosextrasservidor.setor_ingresso.nome)

    if len(servidor.nivel_padrao) >= 3:
        corpo = corpo.replace('###NIVEL_CAPACITACAO###', int_to_roman(servidor.nivel_padrao[0]))
        corpo = corpo.replace('###NIVEL_PROGRESSAO###', servidor.nivel_padrao[1:3])
    corpo = corpo.replace('###JORNADA_TRABALHO###', servidor.jornada_trabalho.nome)
    corpo = corpo.replace('###UO_SERVIDOR###', servidor.setor_exercicio.uo.nome)
    corpo = corpo.replace('###NOME_USUARIO_LOGADO###', servidor_logado.nome)
    corpo = corpo.replace('###MATRICULA_USUARIO_LOGADO###', servidor_logado.matricula)

    # Progressões
    marcador_progressoes = '<li><span style="color:#c0392b">###PROGRESSOES###</span></li>'
    for pca in servidor.pca_set.all().order_by('data_entrada_pca'):
        posicionamentos = pca.posicionamentopca_set.all().order_by('data_inicio_posicionamento_pca', 'posicionamentopcanivel__nivel')
        if posicionamentos.exists():
            x = 0
            max = posicionamentos.count()

            # No 1º posicionamento: se padrão 101, não é progressão; se for 102 ou 201, dá para saber que anterior é 101
            texto_progressao = None
            if posicionamentos[x].posicionamentopcanivel and posicionamentos[x].posicionamentopcanivel.nivel == '102':
                texto_progressao = (
                    'Autorizada a Progressão Funcional, por Mérito, ao servidor, do {}, passando do Padrão de '
                    'Vencimento 01 para o Padrão de Vencimento {}, com efeitos financeiros estabelecidos a partir de '
                    '{}, conforme Portaria nº {}, de {}.'.format(
                        posicionamentos[x].dadosextraspcaservidor.campus_lotacao.nome,
                        posicionamentos[x].dadosextraspcaservidor.nivel[1:3],
                        posicionamentos[x].data_inicio_posicionamento_pca.strftime('%d/%m/%Y'),
                        posicionamentos[x].dadosextraspcaservidor.portaria,
                        posicionamentos[x].dadosextraspcaservidor.data_portaria.strftime('%d/%m/%Y'),
                    )
                )
            if posicionamentos[x].posicionamentopcanivel and posicionamentos[x].posicionamentopcanivel.nivel == '201':
                texto_progressao = (
                    'Autorizada a Progressão Funcional, por Capacitação, ao servidor, do {}, passando do Nível de '
                    'Capacitação I para o Nível de Capacitação {}, com efeitos financeiros estabelecidos a partir de '
                    '{}, conforme Portaria nº {}, de {}.'.format(
                        posicionamentos[x].dadosextraspcaservidor.campus_lotacao.nome,
                        int_to_roman(posicionamentos[x].dadosextraspcaservidor.nivel[0]),
                        posicionamentos[x].data_inicio_posicionamento_pca.strftime('%d/%m/%Y'),
                        posicionamentos[x].dadosextraspcaservidor.portaria,
                        posicionamentos[x].dadosextraspcaservidor.data_portaria.strftime('%d/%m/%Y'),
                    )
                )
            if texto_progressao:
                texto_progressao = f'<li>{texto_progressao}</li>'
                corpo = corpo.replace(marcador_progressoes, texto_progressao + marcador_progressoes)
            # Os demais posicionamentos, se houver, se baseiam no anterior.
            nivel_anterior = posicionamentos[x].dadosextraspcaservidor.nivel
            x += 1
            while x < max:
                if not nivel_anterior:  # Entra aqui se no começo do laço não há nivel_anterior
                    nivel_anterior = posicionamentos[x].dadosextraspcaservidor.nivel
                    x += 1
                    continue
                nivel_novo = posicionamentos[x].dadosextraspcaservidor.nivel
                texto_progressao = None
                # Por mérito
                if nivel_novo[0] == nivel_anterior[0] and nivel_novo[-2:] != nivel_anterior[-2:]:
                    texto_progressao = (
                        'Autorizada a Progressão Funcional, por Mérito, ao servidor, do {}, passando do Padrão de '
                        'Vencimento {} para o Padrão de Vencimento {}, com efeitos financeiros estabelecidos a '
                        'partir de {}, conforme Portaria nº {}, de {}.'.format(
                            posicionamentos[x].dadosextraspcaservidor.campus_lotacao.nome,
                            nivel_anterior[-2:],
                            nivel_novo[-2:],
                            posicionamentos[x].data_inicio_posicionamento_pca.strftime('%d/%m/%Y'),
                            posicionamentos[x].dadosextraspcaservidor.portaria,
                            posicionamentos[x].dadosextraspcaservidor.data_portaria.strftime('%d/%m/%Y'),
                        )
                    )
                # Por capacitação
                if nivel_novo[0] != nivel_anterior[0] and nivel_novo[-2:] == nivel_anterior[-2:]:
                    texto_progressao = (
                        'Autorizada a Progressão Funcional, por Capacitação, ao servidor, do {}, passando do Nível de'
                        ' Capacitação {} para o Nível de Capacitação {}, com efeitos financeiros estabelecidos a '
                        'partir de {}, conforme Portaria nº {}, de {}.'.format(
                            posicionamentos[x].dadosextraspcaservidor.campus_lotacao.nome,
                            int_to_roman(nivel_anterior[0]),
                            int_to_roman(nivel_novo[0]),
                            posicionamentos[x].data_inicio_posicionamento_pca.strftime('%d/%m/%Y'),
                            posicionamentos[x].dadosextraspcaservidor.portaria,
                            posicionamentos[x].dadosextraspcaservidor.data_portaria.strftime('%d/%m/%Y'),
                        )
                    )
                if texto_progressao:
                    texto_progressao = f'<li>{texto_progressao}</li>'
                    corpo = corpo.replace(marcador_progressoes, texto_progressao + marcador_progressoes)
                nivel_anterior = nivel_novo
                x += 1
    corpo = corpo.replace(marcador_progressoes, '')

    # Férias (a partir do ano atual)
    marcador_ferias = '<li><span style="color:#c0392b">###FERIAS###</span></li>'
    txt_ferias = ''
    ano_atual = datetime.now().year
    for ferias in servidor.ferias_set.filter(ano__ano__gte=ano_atual).order_by('ano__ano'):
        txt_ferias += f'<li>{ferias.ano.ano} -'
        parcelas = ferias.parcelaferias_set.all()
        if parcelas:
            for parcela in parcelas:
                txt_ferias += f' {parcela.data_inicio.strftime("%d/%m/%Y")} a {parcela.data_fim.strftime("%d/%m/%Y")},'
        else:
            txt_ferias += f'{ferias.data_inicio_periodo1.strftime("%d/%m/%Y")} a {ferias.data_fim_periodo1.strftime("%d/%m/%Y")},'
            if ferias.data_inicio_periodo2 and ferias.data_fim_periodo2:
                txt_ferias += f' {ferias.data_inicio_periodo2.strftime("%d/%m/%Y")} a {ferias.data_fim_periodo2.strftime("%d/%m/%Y")},'
            if ferias.data_inicio_periodo3 and ferias.data_fim_periodo3:
                txt_ferias += f' {ferias.data_inicio_periodo3.strftime("%d/%m/%Y")} a {ferias.data_fim_periodo3.strftime("%d/%m/%Y")},'

        txt_ferias = f'{txt_ferias[0 : len(txt_ferias) - 1]}.</li>'
    if txt_ferias:
        txt_ferias = f'<li>O servidor tem o(s) seguinte(s) período(s) de férias definido(s):<ul>{txt_ferias}</ul></li>'
    corpo = corpo.replace(marcador_ferias, txt_ferias)

    # Função ativa
    marcador_funcao = '<li><span style="color:#c0392b">###FUNCAO_ATIVA###</span></li>'
    txt_funcao_ativa = ''
    for funcao in servidor.servidorfuncaohistorico_set.atuais().order_by('data_inicio_funcao'):
        txt_funcao_ativa = '<li>O servidor foi {} para desempenhar {} de {} em {}, a partir de {}, conforme Portaria nº {}, de {}.</li>'.format(
            'nomeado' if 'CARGO' in funcao.funcao.nome and 'DIRECAO' in funcao.funcao.nome else 'designado',
            'o Cargo de Direção' if 'CARGO' in funcao.funcao.nome and 'DIRECAO' in funcao.funcao.nome else 'a Função Gratificada',
            funcao.atividade.nome.title(),
            funcao.setor_suap.nome,
            funcao.data_inicio_funcao.strftime('%d/%m/%Y'),
            funcao.dadosextrasfuncaoservidor.portaria,
            funcao.dadosextrasfuncaoservidor.data_portaria.strftime('%d/%m/%Y'),
        )
    corpo = corpo.replace(marcador_funcao, txt_funcao_ativa)

    # Mudança de gênero
    if servidor.pessoa_fisica.sexo == 'F':
        corpo = (
            corpo.replace('ao servidor', 'à servidora')
            .replace('do servidor', 'da servidora')
            .replace('o servidor', 'a servidora')
            .replace('O servidor', 'A servidora')
            .replace('Nomeado', 'Nomeada')
            .replace('Interessado', 'Interessada')
            .replace('Lotado', 'Lotada')
            .replace('Localizado', 'Localizada')
            .replace('designado', 'designada')
            .replace('nomeado', 'nomeada')
        )
    corpo = corpo.replace('no Reitoria', 'na Reitoria').replace('do Reitoria', 'da Reitoria')
    return corpo


# IFMA Fim


def roman_to_int(s):
    rom_val = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    int_val = 0
    for i in range(len(s)):
        if i > 0 and rom_val[s[i]] > rom_val[s[i - 1]]:
            int_val += rom_val[s[i]] - 2 * rom_val[s[i - 1]]
        else:
            int_val += rom_val[s[i]]
    return int_val


def estah_no_pgd_hoje_pgd1_pgd2(servidor):
    # Verifica se o servidor está no PGD HOJE
    # - Considera o PGD 1 e o PGD 2

    if 'pgd' in settings.INSTALLED_APPS:
        from pgd.models import SolicitacaoAdesaoServidor as Adesao_Pgd1

        estah_no_pgd_hoje, adesao = Adesao_Pgd1.estah_no_pgd_hoje(servidor)
        if estah_no_pgd_hoje:
            return estah_no_pgd_hoje, adesao

    if 'pgd2' in settings.INSTALLED_APPS:
        from pgd2.models import SolicitacaoAdesaoServidor as Adesao_Pgd2

        return Adesao_Pgd2.estah_no_pgd_hoje(servidor)

    return False, None


def estah_no_pgd_hoje_pgd2(servidor):
    # Verifica se o servidor está no PGD HOJE
    # - Considera o PGD 2

    estah_no_pgd = False
    if 'pgd2' in settings.INSTALLED_APPS:
        from pgd2.models import SolicitacaoAdesaoServidor as Adesao_Pgd2

        estah_no_pgd, _ = Adesao_Pgd2.estah_no_pgd_hoje(servidor)

    return estah_no_pgd


def periodos_estah_no_pgd1_pgd2(servidor):
    # Verifica os periodos que o servidor esta no PGD
    # - Considera o PGD 1 e o PGD 2
    # - Deve ser utilizado apenas pelo ponto no relatório de frequencia
    periodos_pgd = []

    if 'pgd' in settings.INSTALLED_APPS:
        from pgd.models import SolicitacaoAdesaoServidor as Adesao_Pgd1

        periodos_pgd.extend(Adesao_Pgd1.periodos_estah_no_pgd(servidor))

    if 'pgd2' in settings.INSTALLED_APPS:
        from pgd2.models import SolicitacaoAdesaoServidor as Adesao_Pgd2

        periodos_pgd.extend(Adesao_Pgd2.periodos_estah_no_pgd(servidor))

    return periodos_pgd


def gerar_filtro_por_relacao(modelo: type[Model], campo_lookup: str, titulo_label: str) -> type[SimpleListFilter]:
    """
    Gera uma classe de filtro reutilizável para o Django Admin.

    :param modelo: O modelo base (ex: Setor)
    :param campo_lookup: Lookup completo do campo relacionado (ex: 'setor__sigla')
    :param titulo_label: Nome exibido no admin (ex: 'Setor')
    :return: Subclasse de SimpleListFilter
    """

    class FiltroGenerico(SimpleListFilter):
        title = _(titulo_label)
        parameter_name = campo_lookup

        def lookups(self, request, model_admin):
            valores_distintos = model_admin.model.objects.values_list(campo_lookup, flat=True).distinct()
            return [(valor, valor) for valor in valores_distintos if valor]

        def queryset(self, request, queryset):
            if self.value():
                return queryset.filter(**{self.parameter_name: self.value()})
            return queryset

    return FiltroGenerico


def substituir_marcacoes(texto, dados):
    """
    Substitui as marcações no texto por valores correspondentes no dicionário de dados.
    Exemplo de marcação: {{ NOME_SERVIDOR }}
    Exemplo de dicionário de dados: {'NOME_SERVIDOR': 'João Silva'}
    """

    def substitutor(match):
        chave = match.group(1).strip()
        return str(dados.get(chave, f'{{{{ {chave} }}}}'))

    padrao = r'\{\{\s*(\w+)\s*\}\}'
    return re.sub(padrao, substitutor, texto)


def gerar_nome_unico(nome_original):
    """
    Gera um nome de arquivo único baseado no nome original, adicionando um sufixo UUID.
    Ex.:
        nome_original = "documento.pdf"
        nome_unico = gerar_nome_unico(nome_original)
        print(nome_unico)  # exemplo: documento_3fae9b12.pdf
    """
    nome, extensao = extrair_nome_e_extensao(nome_original)
    sufixo = uuid.uuid4().hex[:8]
    return f'{nome}_{sufixo}{extensao}'


def extrair_nome_e_extensao(nome_arquivo):
    """
    Separa o nome e a extensão de um arquivo, com fallback se o nome for inválido.
    """
    if not nome_arquivo or not nome_arquivo.strip():
        return ('arquivo', '')  # fallback seguro

    nome, extensao = os.path.splitext(nome_arquivo)
    if not nome:
        nome = 'arquivo'
    return (nome, extensao)


def _truncar_para_bytes(texto: str, max_bytes: int) -> str:
    """Trunca ``texto`` para caber em ``max_bytes`` bytes UTF-8 sem quebrar caractere."""
    codificado = texto.encode('utf-8')
    if len(codificado) <= max_bytes:
        return texto
    # ``errors='ignore'`` descarta os bytes de um caractere multibyte cortado ao meio.
    return codificado[:max_bytes].decode('utf-8', errors='ignore')


def truncar_nome_arquivo(nome_original: str, max_length: int = 200) -> str:
    """
    Trunca o nome de um arquivo para caber em ``max_length`` **bytes** (UTF-8),
    preservando a extensão.

    O limite é em bytes (não caracteres) para respeitar o limite de 255 bytes por
    componente de caminho do filesystem (ext4/xfs); como ``len(bytes) >= len(str)``,
    isso também garante o ``varchar`` do banco (ex.: ``Arquivo.nome``/``diretorio``,
    de 255 caracteres). Útil quando o usuário envia um arquivo com nome muito longo.

    Ex.:
        truncar_nome_arquivo('a' * 300 + '.pdf', 200)  # → 196 'a's + '.pdf'
    """
    if not nome_original or len(nome_original.encode('utf-8')) <= max_length:
        return nome_original
    nome, extensao = extrair_nome_e_extensao(nome_original)
    orcamento_nome = max_length - len(extensao.encode('utf-8'))
    # Extensão patológica (maior que o limite): trunca o resultado final.
    if orcamento_nome <= 0:
        return _truncar_para_bytes(nome_original, max_length)
    return f'{_truncar_para_bytes(nome, orcamento_nome)}{extensao}'


def extrai_matricula(matricula):
    """
    Recebe '262180277123' e retorna '277123'
    """
    return str(int(matricula[:12][-7:]))


def base_matricula(matricula: str | None) -> str:
    """Base de 6 dígitos da matrícula SIAPE, que identifica a pessoa.

    Na matrícula SIAPE o dígito inicial é o índice do vínculo e os 6 finais são o
    número da pessoa. Como o PCA de um servidor cedido/requisitado é devolvido pelo
    órgão de origem, ele vem com a matrícula **daquele** órgão: o vínculo 2475472 no
    IFRN corresponde ao provimento 1475472 no INCRA. Casar pela string inteira falha
    em 74 dos 141 vínculos medidos; casar pela base resolve.

    Args:
        matricula: Matrícula SIAPE, com ou sem zeros à esquerda. ``None`` é aceito.

    Returns:
        Os 6 últimos dígitos, ou string vazia quando não há dígito algum.
    """
    digitos = ''.join(caractere for caractere in str(matricula or '') if caractere.isdigit())
    return digitos[-6:]


def is_blank(value):
    """None, string vazia ou somente espaços contam como 'em branco'."""
    if value is None:
        return True
    return bool(isinstance(value, str) and value.strip() == '')


def agrupar_por_matricula(vinculos: Iterable[tuple[str, str]], itens: Iterable[tuple[str, Any]]) -> list[dict[str, Any]]:
    """Distribui itens vindos do SIAPE entre os vínculos do servidor.

    A consulta de afastamentos do SIAPE devolve um bloco por `grMatricula`, de
    modo que um servidor com mais de um vínculo ativo aparece em vários blocos,
    cada um com suas próprias férias e afastamentos. O agrupamento mantém esses
    conjuntos separados na exibição.

    Args:
        vinculos: Duplas `(matricula, nome)` que definem a ordem e o rótulo dos
            grupos. Um vínculo sem itens continua na saída, com a lista vazia,
            para que a tela mostre que ele existe e nada foi encontrado.
        itens: Duplas `(matricula, item)`, em qualquer ordem.

    Returns:
        Uma lista de dicionários `{'matricula': ..., 'nome': ..., 'itens': [...]}`.
        Matrícula que apareça só em `itens` — as duas consultas ao SIAPE são
        independentes e podem divergir — vira um grupo sem nome no fim da lista,
        em vez de ser descartada.
    """
    grupos: dict[str, dict[str, Any]] = {}
    for matricula, nome in vinculos:
        grupos.setdefault(str(matricula), {'matricula': str(matricula), 'nome': nome, 'itens': []})
    for matricula, item in itens:
        grupo = grupos.setdefault(str(matricula), {'matricula': str(matricula), 'nome': '', 'itens': []})
        grupo['itens'].append(item)
    return list(grupos.values())
