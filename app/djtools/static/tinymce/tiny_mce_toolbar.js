document.addEventListener("DOMContentLoaded", function () {
  let BASE = {};
  try {
    const el = document.getElementById("tinymce-default-config");
    if (el) BASE = JSON.parse(el.textContent || "{}");
  } catch (e) {
    console.warn("Tiny default inválido ou ausente:", e);
  }

  function getBaseConfig(el) {
    try {
      const data = el.dataset.mceConf ? JSON.parse(el.dataset.mceConf || "{}") : {};
      return { ...BASE, ...data };
    } catch (e) {
      console.warn("Tiny config inválido:", e);
      return { ...BASE };
    }
  }

  function withExtraItems(items, extraItems) {
    if (items === undefined || items === null) return extraItems;
    const text = Array.isArray(items) ? items.join(" ") : String(items);
    return `${text} ${extraItems}`.trim();
  }

  function withToolbarItems(toolbar, extraItems) {
    const defaultToolbar = "undo redo | bold italic underline | alignleft aligncenter alignright alignjustify | code fullscreen preview";
    const text = toolbar === undefined || toolbar === null ? defaultToolbar : String(toolbar);
    return `${text} ${extraItems}`.trim().replace(/^\|\s*/, "");
  }

  function withOverrides(base, overrides) {
    const out = { ...base, ...overrides };
    delete out.selector; // evita conflito se houver no BASE
    return out;
  }

  function applyNamedFormat(editor, formatName) {
    editor.undoManager.transact(() => {
      editor.formatter.apply(formatName);
    });
    editor.nodeChanged();
  }

  function getCurrentDocumentStyle(editor) {
    const block = editor.dom.getParent(editor.selection.getNode(), "p");
    if (!block) return "Simples";
    const textIndent = editor.dom.getStyle(block, "text-indent", true) || block.style.textIndent;
    return textIndent && textIndent !== "0px" && textIndent !== "0" ? "Parágrafo" : "Simples";
  }

  // Menu-botão "Tabela" persistente na barra principal (com menubar desligada, é o
  // único acesso sempre visível às operações de tabela). Reúne inserir tabela,
  // linha/coluna, propriedades da tabela/célula, alinhamento vertical e mesclar.
  function registrarMenuTabela(editor) {
    const cmd = (name, args) => () => editor.execCommand(name, false, args);
    const valign = (v) => () => editor.execCommand("mceTableApplyCellStyle", false, { "vertical-align": v });
    editor.ui.registry.addMenuButton("tabelasuap", {
      text: "Tabela",
      icon: "table",
      tooltip: "Tabela",
      fetch: function (callback) {
        callback([
          { type: "menuitem", text: "Inserir tabela", icon: "table", onAction: cmd("mceInsertTable", { rows: 2, columns: 2 }) },
          { type: "separator" },
          { type: "menuitem", text: "Propriedades da tabela", onAction: cmd("mceTableProps") },
          { type: "menuitem", text: "Propriedades da célula", onAction: cmd("mceTableCellProps") },
          {
            type: "nestedmenuitem",
            text: "Alinhamento vertical",
            getSubmenuItems: function () {
              return [
                { type: "menuitem", text: "Topo", onAction: valign("top") },
                { type: "menuitem", text: "Meio", onAction: valign("middle") },
                { type: "menuitem", text: "Base", onAction: valign("bottom") },
              ];
            },
          },
          { type: "separator" },
          { type: "menuitem", text: "Inserir linha acima", onAction: cmd("mceTableInsertRowBefore") },
          { type: "menuitem", text: "Inserir linha abaixo", onAction: cmd("mceTableInsertRowAfter") },
          { type: "menuitem", text: "Excluir linha", onAction: cmd("mceTableDeleteRow") },
          { type: "separator" },
          { type: "menuitem", text: "Inserir coluna à esquerda", onAction: cmd("mceTableInsertColBefore") },
          { type: "menuitem", text: "Inserir coluna à direita", onAction: cmd("mceTableInsertColAfter") },
          { type: "menuitem", text: "Excluir coluna", onAction: cmd("mceTableDeleteCol") },
          { type: "separator" },
          { type: "menuitem", text: "Mesclar células", onAction: cmd("mceTableMergeCells") },
          { type: "menuitem", text: "Dividir célula", onAction: cmd("mceTableSplitCells") },
          { type: "separator" },
          { type: "menuitem", text: "Excluir tabela", onAction: cmd("mceTableDelete") },
        ]);
      },
    });
  }

  function initOne(el) {
    if (!el) return;
    if (!el.id) el.id = "tinymce_" + Math.random().toString(36).slice(2);
    if (tinymce.get(el.id)) return;
    const base = getBaseConfig(el);
    const isDocumentBody = el.id === "id_corpo" && el.closest("#editardocumento_form");
    const extraPlugins = [
      "quickbars autosave image code fullscreen preview table searchreplace wordcount lists anchor link pagebreak insertdatetime",
      isDocumentBody ? "autoresize" : "",
    ].filter(Boolean).join(" ");
    const config = withOverrides(base, {
      target: el,
      ...(isDocumentBody ? { min_height: 600, max_height: 0, autoresize_bottom_margin: 20 } : {}),
      menubar: false,
      toolbar_mode: "wrap",
      toolbar_sticky: true,
      // seus extras (ex.: quickbars/autosave etc.)
      plugins: withExtraItems(base.plugins, extraPlugins),
      toolbar: withToolbarItems(
        base.toolbar,
        " | save restoredraft"
      ),
      // Barra de contexto (aparece ao clicar na tabela). Inclui Propriedades da
      // célula e Alinhamento vertical — antes ausentes, o que impedia mudar o
      // valign (ficava preso no `vertical-align: top` do content_style).
      table_toolbar:
        "tableprops tablecellprops tablecellvalign | tablemergecells tablesplitcells | " +
        "tableinsertrowbefore tableinsertrowafter tabledeleterow | " +
        "tableinsertcolbefore tableinsertcolafter tabledeletecol | tabledelete",
      // Menu de botão direito com todas as ações de tabela (paridade com o CKEditor
      // anterior): inserir linha/coluna, propriedades da célula, alinhamento, etc.
      contextmenu: "link table image",
      insertdatetime_formats: ["%H:%M:%S", "%d/%m/%Y", "%I:%M:%S %p"],
      // Handlers/funcs ficam aqui no JS (não no settings).
      // As imagens são embutidas como data URL base64 propositalmente: a
      // validação em validarTags() só aceita imagens base64 (rejeita URLs).
      images_upload_handler: (blobInfo, progress) => {
        return new Promise((resolve, reject) => {
          try {
            const mime = blobInfo.blob().type || "image/png";
            const base64 = blobInfo.base64();
            const url = `data:${mime};base64,${base64}`;
            resolve(url);
          } catch (e) {
            reject(e);
          }
        });
      },
      setup: function (editor) {
        editor.ui.registry.addMenuButton("estilosdocumento", {
          text: "Simples",
          onSetup: function (api) {
            const updateLabel = function () {
              api.setText(getCurrentDocumentStyle(editor));
            };
            editor.on("NodeChange SelectionChange SetContent ExecCommand", updateLabel);
            updateLabel();
            return function () {
              editor.off("NodeChange SelectionChange SetContent ExecCommand", updateLabel);
            };
          },
          fetch: function (callback) {
            callback([
              {
                type: "togglemenuitem",
                text: "Simples",
                active: getCurrentDocumentStyle(editor) === "Simples",
                onAction: function () {
                  applyNamedFormat(editor, "simples");
                },
              },
              {
                type: "togglemenuitem",
                text: "Parágrafo",
                active: getCurrentDocumentStyle(editor) === "Parágrafo",
                onAction: function () {
                  applyNamedFormat(editor, "paragrafo");
                },
              },
            ]);
          },
        });
        editor.ui.registry.addButton("save", {
          text: "Salvar",
          onAction: function () { salvar_editor(editor); },
        });
        registrarMenuTabela(editor);
      },
    });

    tinymce.init(config);
  }

  document.querySelectorAll("textarea.tinymce").forEach(initOne);
});


function salvar_tags(editor) {
    if (!editor.readonly) {
        salvar_editor(editor);
    }
}
const arrImgPermitida = ['png', 'jpg', 'jpeg'];

// Exibe um toast de erro de validação (substitui alert(): estilizado,
// não-bloqueante e legível em dispositivos móveis).
function notificarErroValidacao(mensagem) {
    let container = document.getElementById("suap-tinymce-toasts");
    if (!container) {
        container = document.createElement("div");
        container.id = "suap-tinymce-toasts";
        container.style.cssText = "position:fixed;top:1rem;right:1rem;z-index:99999;display:flex;flex-direction:column;gap:.5rem;max-width:90vw;";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.setAttribute("role", "alert");
    toast.textContent = mensagem;
    toast.style.cssText = "background:#c62828;color:#fff;padding:.75rem 1rem;border-radius:.25rem;box-shadow:0 2px 6px rgba(0,0,0,.3);font-size:.9rem;cursor:pointer;";
    toast.addEventListener("click", () => toast.remove());
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

function salvar_editor(editor) {
    if (validarTags(editor)) {
        const form = editor.getElement().form;
        if (form) {
            form.submit();
        }
    }
}

function validarTags(editor) {
    const content = editor.getContent();

    // validar {{ variavel }}
    const variaveis = content.match(/\{\{([^}]+)\}\}/g);
    if (variaveis) {
        for (let variavel of variaveis) {
            const regexpNames = /{{\s*(\w+)\s*}}/gm;
            if (!regexpNames.exec(variavel)) {
                notificarErroValidacao(`Variável inválida: ${variavel}`);
                return false;
            }
        }
    }

    // checar tags proibidas
    const tags = ['img', 'button', 'input', 'select', 'iframe', 'frame', 'embed', 'object', 'param', 'video', 'audio', 'form'];
    const parser = new DOMParser();
    const doc = parser.parseFromString(content, 'text/html');

    for (let tag of tags) {
        const elements = doc.getElementsByTagName(tag);
        if (elements.length > 0) {
            switch (tag) {
                case 'img':
                    if (arrImgPermitida.length === 0) {
                        notificarErroValidacao('Não são permitidas imagens no conteúdo.');
                        return false;
                    }
                    for (let el of elements) {
                        const src = el.getAttribute('src') || '';
                        if (src.startsWith('data:')) {
                            const formatMatch = src.match(/^data:image\/([a-zA-Z]+);base64,/);
                            if (!formatMatch || !arrImgPermitida.includes(formatMatch[1])) {
                                notificarErroValidacao(`Imagem formato "${formatMatch ? formatMatch[1] : 'desconhecido'}" não permitida.`);
                                return false;
                            }
                        } else {
                            notificarErroValidacao('Não são permitidas imagens por URL.');
                            return false;
                        }
                    }
                    break;
                case 'button':
                case 'input':
                case 'select':
                    notificarErroValidacao('Não são permitidos componentes de formulário HTML no conteúdo.');
                    return false;
                case 'iframe':
                case 'form':
                case 'frame':
                    notificarErroValidacao('Não são permitidos formulários ou iframes no conteúdo.');
                    return false;
                case 'embed':
                case 'object':
                case 'param':
                    notificarErroValidacao('Não são permitidos objetos no conteúdo.');
                    return false;
                case 'video':
                    notificarErroValidacao('Não são permitidos vídeos no conteúdo.');
                    return false;
                case 'audio':
                    notificarErroValidacao('Não é permitido áudio no conteúdo.');
                    return false;
            }
        }
    }
    return true;
}

function validarTodosOsEditores() {
    if (typeof tinymce === 'undefined' || !tinymce.editors) {
        return true;
    }
    // TinyMCE 5 usa array; TinyMCE 6 usa objeto {id: editor} — ambos precisam funcionar.
    const editores = Array.isArray(tinymce.editors) ? tinymce.editors : Object.values(tinymce.editors);
    for (const editor of editores) {
        if (!validarTags(editor)) {
            return false;
        }
    }
    return true;
}
