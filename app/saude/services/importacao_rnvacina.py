import datetime
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from saude.models import CartaoVacinal, HistoricoImportacaoRNVacina, Prontuario, Vacina
from saude.services.rnvacina import ApiRNMaisVacinaService


@dataclass
class ResultadoImportacaoRNVacina:
    quantidade_importada: int = 0
    quantidade_existentes: int = 0
    quantidade_nao_mapeadas: int = 0
    nomes_nao_mapeados: list = field(default_factory=list)
    nomes_vacinas_cadastradas: list = field(default_factory=list)


def get_cpf_do_prontuario(prontuario):
    if not prontuario.vinculo:
        return None
    relacionamento = prontuario.vinculo.relacionamento
    return getattr(relacionamento, 'cpf', None) or getattr(getattr(relacionamento, 'pessoa_fisica', None), 'cpf', None)


def normalizar_nome_vacina(nome):
    return (nome or '').strip().casefold()


def _construir_mapa_vacinas_rnvacina():
    return {
        normalizar_nome_vacina(vacina.nome_rnmaisvacina): vacina
        for vacina in Vacina.ativas.exclude(nome_rnmaisvacina__isnull=True).exclude(nome_rnmaisvacina='')
    }


def resolver_vacina_por_nome_rnvacina(nome_api, mapa_vacinas=None):
    alvo = normalizar_nome_vacina(nome_api)
    if not alvo:
        return None
    mapa_vacinas = _construir_mapa_vacinas_rnvacina() if mapa_vacinas is None else mapa_vacinas
    return mapa_vacinas.get(alvo)


def _obter_ou_cadastrar_vacina(nome_api, mapa_vacinas):
    """
    Se a API retornar uma vacina sem "Nome no RN+Vacina" mapeado, cadastra automaticamente uma
    nova Vacina usando o próprio nome da API — tanto em `nome` quanto em `nome_rnmaisvacina`, para
    que futuras importações (deste ou de outros pacientes) já reconheçam o mesmo nome. O
    coordenador de saúde pode revisar/ajustar o cadastro depois em Cadastros > Vacinas.
    """
    vacina = resolver_vacina_por_nome_rnvacina(nome_api, mapa_vacinas)
    if vacina:
        return vacina, False
    nome = (nome_api or '').strip()
    if not nome:
        return None, False
    vacina, criada = Vacina.objects.get_or_create(nome_rnmaisvacina=nome, defaults={'nome': nome, 'doses': 1})
    if criada:
        # Atualiza o mapa local para que outra dose da mesma vacina, ainda não mapeada, no mesmo
        # payload reaproveite esta vacina em vez de tentar cadastrá-la de novo.
        mapa_vacinas[normalizar_nome_vacina(nome)] = vacina
    return vacina, criada


def parse_numero_dose(dose_str):
    """
    Retorna (numero_dose, eh_reforco). Reforços têm sua própria série.

    Um ordinal colado à palavra "reforço" (ex.: "2º Reforço") identifica qual reforço é. Já em
    textos como "3ª Dose (Reforço)" o número se refere à dose geral, não a um ordinal de reforço —
    mas ainda assim é preservado como numero_dose (em vez de colapsar em 1) para não colidir com
    um "1º Reforço" real do mesmo paciente/vacina e descartar uma dose silenciosamente.
    """
    texto = (dose_str or '').strip().casefold()
    match_ordinal_reforco = re.match(r'(\d+)\s*[ºª°]?\s*reforç', texto)
    if match_ordinal_reforco:
        return int(match_ordinal_reforco.group(1)), True
    if 'reforç' in texto or 'reforc' in texto:
        match_numero_geral = re.match(r'(\d+)', texto)
        if match_numero_geral:
            return int(match_numero_geral.group(1)), True
        return 1, True
    if 'única' in texto or 'unica' in texto:
        return 1, False
    match = re.match(r'(\d+)', texto)
    if match:
        return int(match.group(1)), False
    return None, False


def _parse_data_aplicacao(data_str):
    if not data_str:
        return None
    try:
        return datetime.datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return None


def _processar_imunizacoes(prontuario, dados):
    resultado = ResultadoImportacaoRNVacina()
    mapa_vacinas = _construir_mapa_vacinas_rnvacina()
    for item in dados:
        nome_vacina_api = item.get('vacina')
        numero_dose, eh_reforco = parse_numero_dose(item.get('dose'))
        if numero_dose is None:
            resultado.quantidade_nao_mapeadas += 1
            if nome_vacina_api and nome_vacina_api not in resultado.nomes_nao_mapeados:
                resultado.nomes_nao_mapeados.append(nome_vacina_api)
            continue
        vacina, vacina_cadastrada = _obter_ou_cadastrar_vacina(nome_vacina_api, mapa_vacinas)
        if not vacina:
            resultado.quantidade_nao_mapeadas += 1
            continue
        if vacina_cadastrada and nome_vacina_api not in resultado.nomes_vacinas_cadastradas:
            resultado.nomes_vacinas_cadastradas.append(nome_vacina_api)
        _registrar_ou_reconciliar_dose(prontuario, vacina, numero_dose, eh_reforco, item, resultado)
    return resultado


def _registrar_ou_reconciliar_dose(
    prontuario: Prontuario, vacina: Vacina, numero_dose: int, eh_reforco: bool, item: dict, resultado: ResultadoImportacaoRNVacina
) -> None:
    data_aplicacao = _parse_data_aplicacao(item.get('data_aplicacao'))
    if data_aplicacao and CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina, data_vacinacao=data_aplicacao).exists():
        # Mesma aplicação já registrada com outra numeração (cadastro manual, reforço legado de
        # numero_dose=0 etc.): a data identifica a dose real melhor que o número vindo da API.
        resultado.quantidade_existentes += 1
        return
    obs_importacao = f'Importado do RN+Vacina em {datetime.date.today().strftime("%d/%m/%Y")}'
    registro, criado = CartaoVacinal.objects.get_or_create(
        prontuario=prontuario,
        vacina=vacina,
        numero_dose=numero_dose,
        eh_reforco=eh_reforco,
        defaults={'data_vacinacao': data_aplicacao, 'externo': True, 'obs': obs_importacao},
    )
    if criado:
        resultado.quantidade_importada += 1
    elif not registro.data_vacinacao and data_aplicacao:
        # Reconcilia um aprazamento cadastrado manualmente (sem data de aplicação) com a dose
        # real trazida pela importação, em vez de tratá-lo como duplicidade.
        registro.data_vacinacao = data_aplicacao
        registro.externo = True
        registro.obs = obs_importacao
        registro.save()
        resultado.quantidade_importada += 1
    else:
        resultado.quantidade_existentes += 1


def _registrar_historico(prontuario, vinculo_solicitante, origem, sucesso, quantidade, mensagem):
    tamanho_maximo = HistoricoImportacaoRNVacina._meta.get_field('mensagem').max_length
    if mensagem and len(mensagem) > tamanho_maximo:
        mensagem = mensagem[: tamanho_maximo - 1] + '…'
    HistoricoImportacaoRNVacina.objects.create(
        prontuario=prontuario,
        vinculo_solicitante=vinculo_solicitante,
        origem=origem,
        sucesso=sucesso,
        quantidade_importada=quantidade,
        mensagem=mensagem,
    )


def _montar_mensagem_historico(resultado):
    partes = []
    if resultado.nomes_vacinas_cadastradas:
        partes.append('Vacinas cadastradas automaticamente: ' + ', '.join(resultado.nomes_vacinas_cadastradas))
    if resultado.nomes_nao_mapeados:
        partes.append('Itens não reconhecidos (dose não identificada): ' + ', '.join(resultado.nomes_nao_mapeados))
    return '; '.join(partes) or None


def importar_vacinas_rnvacina(prontuario, vinculo_solicitante, origem):
    """
    Consulta o RN+Vacina pelo CPF do paciente do prontuário e importa as doses novas para o
    cartão vacinal.
    """
    cpf = get_cpf_do_prontuario(prontuario)
    if not cpf:
        _registrar_historico(prontuario, vinculo_solicitante, origem, False, 0, 'CPF não encontrado para este paciente.')
        raise ValidationError('Não foi possível identificar o CPF deste paciente.')

    try:
        dados = ApiRNMaisVacinaService().consultar_imunizacoes(cpf)
    except ValidationError as e:
        _registrar_historico(prontuario, vinculo_solicitante, origem, False, 0, str(e))
        raise

    resultado = _processar_imunizacoes(prontuario, dados)
    _registrar_historico(prontuario, vinculo_solicitante, origem, True, resultado.quantidade_importada, _montar_mensagem_historico(resultado))
    return resultado
