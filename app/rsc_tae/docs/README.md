# Documentação do módulo RSC-TAE

## Arquivos

- **especificacoes.md** — Especificação completa do módulo baseada no Relatório CNS 01/2026 (níveis, requisitos, 89 critérios, fluxo, gap analysis, changelog).
- **SKILL.md** — Skill do GitHub Copilot para o módulo RSC-TAE.

## Skill do Copilot (SKILL.md)

O arquivo `SKILL.md` contém instruções detalhadas que permitem ao GitHub Copilot atuar como especialista no módulo RSC-TAE. Ele cobre modelos, views, templates, enums, permissões, fluxo de processo e integração com djtools.

### Como ativar

Para que o Copilot reconheça a skill automaticamente, ela precisa estar em um dos diretórios padrão na **raiz do projeto**:

```
.github/skills/rsc-tae/SKILL.md
```

**Procedimento:**

1. Copie o arquivo para o diretório correto (se ainda não existir):
   ```bash
   mkdir -p .github/skills/rsc-tae
   cp rsc_tae/docs/SKILL.md .github/skills/rsc-tae/SKILL.md
   ```

2. A pasta `.github` está no `.gitignore`, então a skill é **local** e não será versionada.

3. Após copiar, a skill será:
   - **Ativada automaticamente** quando suas perguntas mencionarem termos como "rsc_tae", "avaliação", "processo RSC", "djtools", "multi-avaliador", etc.
   - **Invocável manualmente** digitando `/rsc-tae` no chat do Copilot.

### Atualizando a skill

Sempre que alterar o `SKILL.md` em `rsc_tae/docs/`, lembre-se de copiar novamente para `.github/skills/rsc-tae/SKILL.md` para que as mudanças sejam reconhecidas pelo Copilot.
