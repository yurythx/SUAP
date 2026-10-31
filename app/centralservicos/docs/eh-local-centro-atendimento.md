# `eh_local` — Centro de Atendimento

## O que é

`eh_local` é um booleano do modelo `CentroAtendimento` (`centralservicos/models.py:94`, default `False`) que marca se aquele Centro de Atendimento é **vinculado a um campus específico** (local) ou **compartilhado entre todos os campi** (não-local).

`CentroAtendimento` tem `unique_together = ('nome', 'area')` (`centralservicos/models.py:98`), ou seja, já é escopado por **Área de Serviço** (`AreaAtuacao`), independente do valor de `eh_local`. Não existe "um único `CentroAtendimento` no sistema todo" — podem existir vários, um por área (ou até vários por área, com nomes diferentes).

O que `eh_local` diferencia é **dentro de uma mesma Área/Centro**, se o atendimento é fatiado por campus ou não:

- **`eh_local=False`**: o Centro de Atendimento (daquela área) é **único por área, mas compartilhado entre todos os campi**. Basta existir **um** `GrupoAtendimento` de primeiro nível para esse centro — não importa de qual campus é o interessado, o chamado cai sempre no mesmo grupo.
- **`eh_local=True`**: o mesmo Centro de Atendimento precisa de **um `GrupoAtendimento` por campus**. O roteamento passa a considerar o campus do interessado, e o centro só fica disponível para os campi que efetivamente têm um `GrupoAtendimento` cadastrado nele.

Resumindo: "único" não é "único no sistema", é **"um atendimento só, para todos os campi daquela área"** — em oposição a "um atendimento diferente por campus".

## Diferença prática (onde o campo é usado)

### 1. Roteamento do chamado — `GrupoAtendimento.get_grupo_primeiro_nivel` (`centralservicos/models.py:377-401`)

```python
queryset = GrupoAtendimento.objects.filter(centro_atendimento=centro, atendentes__isnull=False)
if centro.eh_local:
    queryset = queryset.filter(campus=uo)...   # considera o campus
else:
    ...                                          # ignora o campus, grupo único
```

- `eh_local=True`: filtra os grupos de atendimento **pelo campus** (`uo`) informado.
- `eh_local=False`: o campus é ignorado — existe um único grupo de primeiro nível para o centro, compartilhado por todos os campi.

Usado toda vez que um chamado é aberto (`Chamado.save`, `centralservicos/models.py:1118`) para decidir a quem atribuir.

### 2. Lista de centros disponíveis para um serviço — `Servico.get_centros_atendimento` (`centralservicos/models.py:276-281`)

```python
self.centros_atendimento.filter(Q(eh_local=False) | Q(eh_local=True, grupoatendimento__campus_id=campus_id))
```

- Centros **não-locais** (`eh_local=False`) aparecem sempre, para qualquer campus.
- Centros **locais** (`eh_local=True`) só aparecem se existir um `GrupoAtendimento` daquele centro **naquele campus** específico do usuário — ou seja, um centro local "não existe" para um campus sem grupo de atendimento cadastrado.

### 3. Validação de reclassificação de chamado — `forms.py:711`

```python
not centro_atendimento_old.eh_local or str(chamado.campus.id) == str(self.cleaned_data.get('uo'))
```

Só considera "sem mudança real" na reclassificação se o centro **não for local**, ou se for local mas o campus continuar o mesmo — porque um centro local depende do campus para fazer sentido.

## Exemplo de uso real

`centralservicos_configurarDIAAC.py:30-34` cria um `CentroAtendimento` chamado "Campus" com `eh_local=True`, para atendimento descentralizado por campus (em oposição a um centro central único, como "DIAAC").
