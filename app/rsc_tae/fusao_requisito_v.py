"""Lógica de fusão dos 8 itens do Requisito V em 4 canônicos (titular/substituto vira o ``papel``).

Compartilhada entre o management command ``migrar_papel_requisito_v`` (uso manual / dry-run) e a
data migration que roda no deploy. Por isso recebe as CLASSES de model por parâmetro: o command
passa os models reais e a migration passa ``apps.get_model(...)`` (models históricos).

IMPORTANTE (models históricos): não usar constantes/propriedades/métodos do model real. Só campos
e travessia de FK. Por isso: papéis como literais ``'titular'``/``'substituto'`` e a taxa do
substituto lida de ``substituto.grupo.pontuacao_unidade`` (campo do grupo), não da property
``item.pontuacao_unidade``.
"""

import re

REQUISITO_V = 5
PAPEL_TITULAR = 'titular'
PAPEL_SUBSTITUTO = 'substituto'
_SUFIXO = re.compile(r'^(?P<base>.*?)\s*[—-]\s*(?P<papel>titular|substituto)\s*$', re.IGNORECASE)


def parear_requisito_v(RolSaberCompetencia):
    """Lista (base, item_titular, item_substituto) dos pares ATIVOS do Requisito V (casa por título)."""
    itens = RolSaberCompetencia.objects.filter(grupo__requisito__numero=REQUISITO_V, ativo=True).select_related('grupo')
    por_base: dict = {}
    for item in itens:
        m = _SUFIXO.match(item.titulo or '')
        if not m:
            continue
        por_base.setdefault(m.group('base').strip(), {})[m.group('papel').lower()] = item

    pares = []
    for base, d in por_base.items():
        titular, substituto = d.get(PAPEL_TITULAR), d.get(PAPEL_SUBSTITUTO)
        if titular and substituto:
            pares.append((base, titular, substituto))
    return pares


def _reapontar_preenchimentos(RolSaberCompetenciaPreenchimento, titular, substituto) -> int:
    """Move os preenchimentos do substituto para o titular, somando na colisão de (vínculo, item)."""
    total = 0
    for pre in RolSaberCompetenciaPreenchimento.objects.filter(rol_saber_competencia=substituto):
        existente = RolSaberCompetenciaPreenchimento.objects.filter(vinculo=pre.vinculo, rol_saber_competencia=titular).first()
        if existente:
            existente.quantidade = (existente.quantidade or 0) + (pre.quantidade or 0)
            existente.save(update_fields=['quantidade'])
            pre.delete()
        else:
            pre.rol_saber_competencia = titular
            pre.save(update_fields=['rol_saber_competencia'])
        total += 1
    return total


def fundir_par(RolSaberCompetenciaAnexo, RolSaberCompetenciaPreenchimento, titular, substituto) -> dict:
    """Funde um par: taxa do substituto no titular, repontar anexos/preenchimentos, desativar substituto."""
    base = _SUFIXO.match(titular.titulo or '')
    titular.aceita_papel = True
    titular.pontuacao_unidade_substituto = substituto.grupo.pontuacao_unidade
    titular.titulo = base.group('base').strip() if base else titular.titulo
    titular.save(update_fields=['aceita_papel', 'pontuacao_unidade_substituto', 'titulo'])

    n_tit = RolSaberCompetenciaAnexo.objects.filter(rol_saber_competencia=titular).update(papel=PAPEL_TITULAR)
    n_sub = RolSaberCompetenciaAnexo.objects.filter(rol_saber_competencia=substituto).update(rol_saber_competencia=titular, papel=PAPEL_SUBSTITUTO)
    n_pre = _reapontar_preenchimentos(RolSaberCompetenciaPreenchimento, titular, substituto)

    substituto.ativo = False
    substituto.save(update_fields=['ativo'])
    return {'anexos_titular': n_tit, 'anexos_substituto': n_sub, 'preenchimentos': n_pre}


def fundir_requisito_v(RolSaberCompetencia, RolSaberCompetenciaAnexo, RolSaberCompetenciaPreenchimento, escrever=None):
    """Funde todos os pares ativos do Requisito V. ``escrever`` (opcional) recebe linhas de log. Retorna a lista de pares processados."""
    pares = parear_requisito_v(RolSaberCompetencia)
    for base, titular, substituto in pares:
        info = fundir_par(RolSaberCompetenciaAnexo, RolSaberCompetenciaPreenchimento, titular, substituto)
        if escrever:
            escrever(
                f'- Par "{base}": titular #{titular.pk} + substituto #{substituto.pk} | '
                f'anexos {info["anexos_titular"]} titular / {info["anexos_substituto"]} substituto; '
                f'preenchimentos {info["preenchimentos"]}; substituto desativado.'
            )
    return pares
