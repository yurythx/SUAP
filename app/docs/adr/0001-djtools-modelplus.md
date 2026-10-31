# ADR-0001 — djtools e ModelPlus como camada-framework do SUAP

- **Status:** aceito
- **Data:** 2026-05-25 (registro retroativo)
- **Decisores:** equipe COSINF/IFRN

## Contexto

O SUAP começou ainda na era do Django 1.x e foi acumulando padrões repetidos entre apps: campos automáticos (criado em / criado por), admin com listas customizadas, geração de PDF, exportação para Excel, tabelas paginadas, integração com formulários "Plus" (ModelFormPlus, ChoiceFieldPlus), middleware de auditoria e permissão, helpers de resposta HTTP (`httprr`), e um conjunto de utilidades de processamento assíncrono.

Sem uma camada própria, cada app reimplementava esses padrões com pequenas variações, levando a:

- Comportamento inconsistente entre telas (paginação, busca, export).
- Dificuldade de evoluir o admin de forma centralizada.
- Acoplamento direto a Django interno em centenas de lugares — impossível atualizar o framework sem mexer em todo lado.

## Decisão

Tratar **`djtools` como camada-framework interna do SUAP**, posicionada antes de `django.contrib.admin` em `INSTALLED_APPS` (via `PRE_INSTALLED_APPS_SUAP`). Toda model do projeto herda de `djtools.db.models.ModelPlus`, não de `django.db.models.Model`. Toda admin custom herda de `ModelAdminPlus`, não de `ModelAdmin`. Forms usam `ModelFormPlus` e os campos `*Plus`.

A regra é prática: ao criar uma nova entidade, o caminho é `from djtools.db import models; class Foo(models.ModelPlus): ...`.

## Consequências

**Positivas**

- Mudanças cross-cutting (auditoria, soft delete, novos campos automáticos) acontecem em um lugar.
- Tabelas, exports, admin têm comportamento previsível.
- O monolito tem um ponto único de extensão para integrar funcionalidades novas (PDFs padrão, response helpers).

**Negativas / a aceitar**

- Onboarding mais lento: quem chega esperando Django "puro" se confunde.
- Acoplamento ao `djtools` é forte: trocar a stack web é mais caro do que em um Django padrão.
- O `pyright` só consegue tipar de fato `djtools`, `comum` e `suap` — outros apps são `# type: ignore` implícito (`pyrightconfig.json`). Aceito como trade-off pela cobertura cirúrgica.

## Alternativas rejeitadas

- **Usar Django puro + mixins por funcionalidade.** Tentado em alguns apps antigos; gerou inconsistência e duplicação.
- **Quebrar `djtools` em pacote PyPI separado.** Custo operacional alto e ganho marginal — o monolito é deploy único.
- **Migrar para outro framework (FastAPI etc.).** Inviável para o tamanho do projeto sem reescrita completa.

## Como tocar nessa decisão

Reabrir esta ADR antes de:

- Introduzir um novo padrão de modelo que não herde de `ModelPlus`.
- Mover lógica de `djtools` para um pacote externo.
- Reorganizar `INSTALLED_APPS` de forma que `djtools` não venha mais antes de `django.contrib.admin`.

Mudanças locais (adicionar um helper a `djtools`, ajustar um campo `Plus`) **não** exigem nova ADR.
