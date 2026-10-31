# Fluxo: anexar documentos

> Fluxo de associação de documentos textuais ou digitalizados a um documento pai e composição do arquivo de saída.

- **Ator:** usuário com permissão de edição/anexação.
- **Gatilho:** seleção de documentos na operação de anexação.
- **Pré-condições:** documento pai editável, anexos acessíveis e tipo/modelo permitindo anexação quando aplicável.
- **Pós-condições:** relação de anexo persistida; ao gerar arquivo, anexos podem ser incorporados ao PDF.
- **Depende de:** modelos de relação de anexo, acesso do documento pai, arquivos e gerador de PDF.
- **Habilita:** visualização/impressão do documento composto e operações de desanexação.
- **Entrada no código:** rotas de listar/anexar/desanexar, `DocumentoTextoAnexo*`, `DocumentoTexto.get_pdf()` e `utils.py`.

```mermaid
sequenceDiagram
    actor A as Usuário autorizado
    participant V as Views de anexação
    participant P as Documento pai
    participant F as Documento filho
    participant R as Relação de anexo
    participant PDF as Gerador de PDF

    A->>V: Solicita documentos anexáveis
    V->>P: Verifica acesso e editabilidade
    V->>F: Filtra documentos compatíveis e acessíveis
    F-->>V: Lista de candidatos
    A->>V: Confirma anexação
    V->>R: Persiste relação pai-filho
    R-->>V: Anexo registrado
    A->>V: Solicita visualização/impressão
    V->>P: get_pdf()
    P->>PDF: Renderiza conteúdo do pai
    PDF->>F: Renderiza e mescla anexos
    PDF-->>V: PDF composto
    A->>V: Desanexa, se necessário
    V->>R: Remove relação
```

## Observações

- Há relações específicas para documento textual e digitalizado.
- Anexo simples digitalizado segue regras do documento pai e é tratado separadamente dos demais documentos.
- A geração de PDF pode incluir anexos e a conversão para PDF/A é assíncrona.
- ⚠️ REVISAR: o código contempla restrições adicionais ligadas a processo eletrônico; confirmar a matriz de quais tipos de documento podem ser anexados em cada contexto.

Gerado/atualizado via subagent `documentador` em 2026-09-09.
