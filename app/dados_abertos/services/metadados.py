"""Metadados DCAT-BR do conjunto de dados, no formato em que sobem ao CKAN.

O CKAN só tem campos nativos para título, descrição, tags, licença, contato e versão; o restante do
DCAT-BR (periodicidade, cobertura, observância legal, ODS) vai nos ``extras`` do package. As chaves
seguem as do formulário de catalogação do dados.gov.br, para que o portal federal as reconheça.

Os campos estruturados do model prevalecem sobre os ``extras`` livres da base: uma chave digitada
à mão no JSON com o mesmo nome não pode contradizer o que o formulário validou.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dados_abertos.enums import ODS, Periodicidade
from dados_abertos.services.periodicidade import frequencia_mais_estrita

if TYPE_CHECKING:
    import datetime

    from dados_abertos.models import BaseDados

IDIOMA = 'pt-BR'


def periodicidade(base: BaseDados) -> str:
    """Periodicidade declarada da base: a mais estrita entre os PDAs em que ela está.

    A base é um único conjunto no CKAN e só pode anunciar uma cadência; vale a promessa mais curta,
    a mesma régua da rotina de atualização (``periodicidade.frequencia_mais_estrita``).

    Returns:
        str: Rótulo da periodicidade, ou vazio quando nenhum PDA a define.
    """
    frequencias = [f for f in base.relacoes_pda.values_list('frequencia_atualizacao', flat=True) if f]
    if not frequencias:
        return ''
    # Só EVENTUAL (sem intervalo) não é ausência de declaração: o PDA prometeu atualizar sob demanda.
    escolhida = frequencia_mais_estrita(frequencias) or Periodicidade.EVENTUAL
    return Periodicidade.LABELS[escolhida].upper()


def _booleano(valor: bool) -> str:
    return 'true' if valor else 'false'


def _data(valor: datetime.date | None) -> str:
    return valor.isoformat() if valor else ''


def extras_dcat(base: BaseDados) -> dict[str, str]:
    """Extras do package: os livres da base, sobrescritos pelos campos DCAT-BR preenchidos.

    Chave com valor vazio fica de fora, para não publicar campo em branco como se fosse informação.
    """
    estruturados = {
        'periodicidade': periodicidade(base),
        'tema': base.tema.nome if base.tema_id else '',
        'idioma': IDIOMA,
        'coberturaEspacial': base.cobertura_espacial,
        'valorCoberturaEspacial': base.valor_cobertura_espacial,
        'granularidadeEspacial': base.granularidade_espacial,
        'coberturaTemporalInicio': _data(base.cobertura_temporal_inicio),
        'coberturaTemporalFim': _data(base.cobertura_temporal_fim),
        'observanciaLegal': base.observancia_legal,
        'ods': '; '.join(ODS.rotulo(n) for n in sorted(base.ods or [])),
        'dadosGenero': _booleano(base.dados_genero),
        'dadosRacaEtnia': _booleano(base.dados_raca_etnia),
    }
    # O campo aceita qualquer JSON; uma lista (o formato de extras do próprio CKAN, colado à mão)
    # derrubaria o sync e as telas da base. Fora do formato de dicionário, os livres são ignorados.
    livres = {k: str(v) for k, v in base.extras.items()} if isinstance(base.extras, dict) else {}
    return {k: v for k, v in {**livres, **estruturados}.items() if v}


def payload_dataset(base: BaseDados) -> dict:
    """Payload do package para ``package_create``/``package_patch``.

    Os metadados de contato, licença e versão só entram quando preenchidos: o patch compara apenas as
    chaves presentes, e mandar vazio apagaria no portal o que foi cadastrado lá ou por uma licença
    ainda sem ``codigo_ckan``. Título, descrição e organização seguem sempre, como antes.
    """
    opcionais = {
        'license_id': base.licenca.codigo_ckan if base.licenca_id else '',
        'author': base.autor,
        'author_email': base.autor_email,
        'maintainer': base.mantenedor,
        'maintainer_email': base.mantenedor_email,
        'version': base.versao,
    }
    return {
        'name': base.nome,
        'title': base.titulo or base.nome,
        'notes': base.notas or '',
        'owner_org': base.organizacao.id_remoto if base.organizacao_id else None,
        **{k: v for k, v in opcionais.items() if v},
        'extras': [{'key': k, 'value': v} for k, v in extras_dcat(base).items()],
        'tags': [{'name': t} for t in (base.tags or [])],
    }


#: Campos escalares comparados no patch de um package já existente, quando presentes no payload.
CAMPOS_ESCALARES = ('title', 'notes', 'owner_org', 'license_id', 'author', 'author_email', 'maintainer', 'maintainer_email', 'version')
