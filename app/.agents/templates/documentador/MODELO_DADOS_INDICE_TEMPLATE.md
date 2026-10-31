# Modelo de dados — {{Módulo}}

> Módulo grande: o modelo está particionado por **subdomínio**. Como derivar:
> - se `models/` for um **pacote** (ex.: `edu/models/matricula.py`), cada submódulo é um subdomínio;
> - se for um **`models.py` único**, agrupe por **clusters de nome/relação** + agrupamento do `admin.py` (inferência — marque `⚠️ REVISAR`).
>
> Cada sub-área tem seu próprio ERD; este índice dá a visão macro e como as áreas
> se conectam.

## Subdomínios

```mermaid
graph TD
    SubA[{{Matrícula}}] --> SubB[{{Diário}}]
    SubA --> SubC[{{Aluno}}]
```

| Subdomínio | Entidades principais | ERD |
|---|---|---|
| {{Matrícula}} | {{Matrícula, MatrículaPeriodo}} | [matricula.md](matricula.md) |
| {{> ⚠️ REVISAR: agrupamento inferido (sem pacote `models/`)}} | {{...}} | {{...}} |

---
_Gerado/atualizado via subagent `documentador` em {{AAAA-MM-DD}}._
