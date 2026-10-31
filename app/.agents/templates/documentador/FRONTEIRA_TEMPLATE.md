# Fronteiras — {{Módulo}}

> Superfície do módulo: o que entra, o que sai e os contratos com o resto do SUAP.
> Complementa o [HLA.md](HLA.md) (§1 contexto, §5 integrações).

## Mapa

```mermaid
graph LR
    In1[{{app_consumidor}}] --> Mod[{{Módulo}}]
    Mod --> Out1[{{edu/rh/comum}}]
    Mod --> Ext1[{{documento_eletronico / MinIO}}]
```

## Dependências de entrada (inbound)

Módulos que importam/usam este. Derive de
`grep -rl "import {{modulo}}\|from {{modulo}}" . --include=*.py` (excluindo o próprio
módulo e `migrations/`).

| Módulo consumidor | O que consome | Acoplamento |
|---|---|---|
| {{app}} | {{model / função / template}} | {{forte / fraco (ex.: import lazy)}} |

_Ninguém depende deste módulo:_ `_N/A — folha_`

## Dependências de saída (outbound)

Confira contra `module_dependencies.json`.

| Depende de | O quê | Tipo |
|---|---|---|
| {{edu/rh/comum}} | {{models/funcs}} | {{módulo interno}} |
| {{djtools}} | {{ModelPlus, forms, assincrono, utils}} | {{framework SUAP}} |
| {{documento_eletronico}} | {{...}} | {{integração condicional (`in INSTALLED_APPS`)}} |

## Contratos publicados

O que outros módulos podem acoplar a este (mude com cuidado):

- **Signals emitidos/ouvidos:** {{...}}
- **Models reusados por outros módulos:** {{...}}
- **Funções / services / templates públicos:** {{...}}
- **Tasks/agendamento que outros dependem:** {{...}}
- {{> ⚠️ REVISAR: contrato implícito não óbvio no código (ex.: acoplamento por id numérico, sem FK)}}

---
_Gerado/atualizado via subagent `documentador` em {{AAAA-MM-DD}}._
