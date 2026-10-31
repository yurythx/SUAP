/**
 * Pincel de formatação (Format Painter) para o TinyMCE 6.
 *
 * O plugin oficial de Format Painter é premium no TinyMCE 6 e não carrega na
 * versão GPL self-hosted do SUAP. Este é um plugin externo próprio (mesmo padrão
 * do plugin `case`) que reproduz o comportamento de "copiar e colar formatação":
 *
 *   1. Selecione um trecho já formatado e clique no botão (o botão fica ativo).
 *   2. Selecione o texto de destino — a formatação é aplicada e o pincel desarma.
 *
 * Clique no botão novamente (ou tecle Esc) enquanto ativo para cancelar.
 *
 * Copia as propriedades de formatação inline resolvidas (computed) do início da
 * seleção e as reaplica envolvendo o destino em um <span> via editor.formatter.
 */
(function () {
    'use strict';

    // Propriedades de formatação inline copiadas pelo pincel.
    const STYLE_PROPS = [
        'font-family',
        'font-size',
        'font-weight',
        'font-style',
        'text-decoration',
        'color',
        'background-color',
        'vertical-align',
        'text-transform',
        'letter-spacing',
    ];

    const FORMAT_NAME = 'suapformatpaint';

    // Ícone próprio (rolo de pintura): a versão open source do TinyMCE não traz
    // um ícone de format painter.
    const ICON =
        '<svg width="24" height="24" viewBox="0 0 24 24">' +
        '<path d="M18 2H5a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1V6h1v4H9v3a1 1 0 0 0 1 1h1v7a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-7h1a1 1 0 0 0 1-1v-1h3V4h-3V3a1 1 0 0 0-1-1z" fill-rule="evenodd"/>' +
        '</svg>';

    tinymce.PluginManager.add('formatpainter', function (editor) {
        let captured = null; // objeto de estilos copiados
        let armed = false; // pincel pronto para aplicar
        let buttonApi = null; // referência ao botão para alternar estado ativo

        // Mantém um valor de estilo? Descarta vazios e valores "neutros" que, se
        // aplicados, sujariam o destino (ex.: fundo transparente, sublinhado none).
        function shouldKeep(prop, value) {
            if (!value) return false;
            const v = String(value).trim().toLowerCase();
            if (v === '' || v === 'normal' || v === 'none' || v === 'auto') return false;
            if (prop === 'text-decoration' && v.indexOf('none') === 0) return false;
            if (prop === 'letter-spacing' && v === '0px') return false;
            if (prop === 'background-color' && (v === 'transparent' || v.indexOf('rgba(0, 0, 0, 0)') === 0)) return false;
            return true;
        }

        function captureFromSelection() {
            const selectionNode = editor.selection.getStart();
            if (!selectionNode) return null;
            const element = selectionNode.nodeType === 1 ? selectionNode : selectionNode.parentElement;
            if (!element || !editor.getBody().contains(element)) return null;

            const computedStyle = editor.getWin().getComputedStyle(element);
            const styles = {};
            STYLE_PROPS.forEach(function (prop) {
                const value = computedStyle.getPropertyValue(prop);
                if (shouldKeep(prop, value)) {
                    styles[prop] = value;
                }
            });
            return Object.keys(styles).length ? styles : null;
        }

        function setArmed(value) {
            armed = value;
            if (buttonApi) buttonApi.setActive(value);
        }

        function disarm() {
            captured = null;
            setArmed(false);
        }

        function arm() {
            const styles = captureFromSelection();
            if (!styles) {
                editor.notificationManager.open({ text: 'Nenhuma formatação encontrada para copiar.', type: 'info', timeout: 3000 });
                return;
            }
            captured = styles;
            setArmed(true);
        }

        function applyCaptured() {
            if (!captured || editor.selection.isCollapsed()) return;
            editor.undoManager.transact(function () {
                editor.formatter.register(FORMAT_NAME, { inline: 'span', styles: captured });
                editor.formatter.apply(FORMAT_NAME);
            });
            disarm();
        }

        // Ao soltar o mouse / teclado com uma seleção expandida, aplica e desarma.
        function onSelectionDone() {
            if (armed) applyCaptured();
        }

        editor.ui.registry.addIcon('format-painter', ICON);

        editor.ui.registry.addToggleButton('formatpainter', {
            icon: 'format-painter',
            tooltip: 'Pincel de formatação: copia a formatação da seleção e aplica no próximo trecho selecionado',
            onAction: function () {
                if (armed) {
                    disarm();
                } else {
                    arm();
                }
            },
            onSetup: function (api) {
                buttonApi = api;
                api.setActive(armed);
                editor.on('mouseup', onSelectionDone);
                editor.on('keyup', onSelectionDone);
                return function () {
                    buttonApi = null;
                    editor.off('mouseup', onSelectionDone);
                    editor.off('keyup', onSelectionDone);
                };
            },
        });

        // Esc cancela o pincel quando ativo.
        editor.on('keydown', function (e) {
            if (armed && e.keyCode === 27) {
                disarm();
            }
        });

        editor.addCommand('mceFormatPainterCancel', disarm);

        return {
            getMetadata: function () {
                return { name: 'Format Painter (SUAP)' };
            },
        };
    });
})();
