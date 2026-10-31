/**
 * @copyright ©Melqui Brito. All rights reserved.
 * @author Melqui Brito
 * @version 1.2.0 (2020-03-08)
 * @description Tinymce custom plugin for changing text case.
 */

(function () {
    tinymce.PluginManager.add('case',
        function (editor) {

            const strings = {
                TOOLNAME: 'Change Case',
                LOWERCASE: 'lowercase',
                UPPERCASE: 'UPPERCASE',
                SENTENCECASE: 'Sentence case',
                TITLECASE: 'Title Case'
            }, defaultTitleCaseExeptions = [
                'at', 'by', 'in', 'of', 'on', 'up', 'to', 'en', 're', 'vs',
                'but', 'off', 'out', 'via', 'bar', 'mid', 'per', 'pro', 'qua', 'til',
                'from', 'into', 'unto', 'with', 'amid', 'anit', 'atop', 'down', 'less', 'like', 'near', 'over', 'past', 'plus', 'sans', 'save', 'than', 'thru', 'till', 'upon',
                'for', 'and', 'nor', 'but', 'or', 'yet', 'so', 'an', 'a', 'some', 'the'
            ], getParameterArray = function (param) {
                let value = editor.getParam(param);
                if (value) {
                    if (Array.isArray(value)) {
                        return value;
                    } else if (typeof value === "string") {
                        return value.replace(/(\s{1,})/g, "?").trim().split('?');
                    }
                }
                if (param === 'title_case_minors') {
                    return defaultTitleCaseExeptions
                }
                return false
            }

            var titleCaseExceptions = getParameterArray('title_case_minors'),
                toInclude = getParameterArray('include_to_title_case_minors'), 
                toRuleOut = getParameterArray('rule_out_from_title_case_minors');
            if (toInclude) {
                toInclude.forEach((el) => {
                    if(defaultTitleCaseExeptions.indexOf(el) === -1) {
                        defaultTitleCaseExeptions.push(el)
                    }
                })
            }
            if (toRuleOut) {
                toRuleOut.forEach((el) => {
                    defaultTitleCaseExeptions = defaultTitleCaseExeptions.filter(minor => minor !== el)
                })
            }
            /*
             * Funções locais de transformação de caixa (evita poluir String.prototype).
             */
            const toSentenceCase = function (str) {
                return str.toLowerCase().replace(/(^\s*\w|[\.\!\?]\s*\w)/g, function (c) {
                    return c.toUpperCase()
                });
            }
            const toTitleCase = function (str) {
                let tt = (text) => {
                    let s = text.split('.');
                    for (let i in s) {
                        let w = s[i].split(' '),
                            j = 0;

                        if (s[i].trim().replace(/(^\s+|\s+$)/g, "").length > 0) {
                            for (j; j < w.length; j++) {
                                let found = false;
                                for (let k = 0; k < w[j].length; k++) {
                                    if (w[j][k].match(/([a-z'áàâãäéèêëíìîïóòôõöúùûü])/i)) {
                                        w[j] = w[j][k].toUpperCase() + w[j].slice(k + 1);
                                        found = true;
                                        break;
                                    }
                                }
                                if (found) {
                                    break;
                                }
                            }
                            for (j; j < w.length; j++) {
                                if (titleCaseExceptions.indexOf(w[j]) === -1) {
                                    for (let k = 0; k < w[j].length; k++) {
                                        if (w[j][k].match(/([a-z'áàâãäéèêëíìîïóòôõöúùûü])/i)) {
                                            w[j] = w[j][k].toUpperCase() + w[j].slice(k + 1);
                                            break;
                                        }
                                    }
                                }
                            }
                            s[i] = w.join(' ');
                        }
                    }
                    return s.join('.');
                };
                return tt(str.toLowerCase());
            }

            const applyCase = function (str, method) {
                switch (method) {
                    case strings.LOWERCASE:
                        return str.toLowerCase();
                    case strings.UPPERCASE:
                        return str.toUpperCase();
                    case strings.SENTENCECASE:
                        return toSentenceCase(str);
                    case strings.TITLECASE:
                        return toTitleCase(str);
                    default:
                        return str;
                }
            }

            const handler = function (node, method, r) {
                if (r.first && r.last) {
                    node.textContent = node.textContent.slice(0, r.startOffset) + applyCase(node.textContent.slice(r.startOffset, r.endOffset), method) + node.textContent.slice(r.endOffset);
                } else if (r.first && !r.last) {
                    node.textContent = node.textContent.slice(0, r.startOffset) + applyCase(node.textContent.slice(r.startOffset), method);
                } else if (!r.first && r.last) {
                    node.textContent = applyCase(node.textContent.slice(0, r.endOffset), method) + node.textContent.slice(r.endOffset);
                } else {
                    node.textContent = applyCase(node.textContent, method);
                }
            }
            
            const apply = function (method) {
                let rng = editor.selection.getRng(),
                    bm = editor.selection.getBookmark(2, true),
                    walker = new tinymce.dom.TreeWalker(rng.startContainer),
                    first = rng.startContainer, 
                    last = rng.endContainer, 
                    startOffset = rng.startOffset, 
                    endOffset = rng.endOffset,
                    current = walker.current();

                do {
                    if (current.nodeName === '#text') {
                        handler(current, method, {
                            first: current === first,
                            last: current === last,
                            startOffset: startOffset,
                            endOffset: endOffset
                        });
                    }
                    if(current === last) {
                        break;
                    }
                    current = walker.next();
                } while (current);
                editor.save();
                editor.isNotDirty = true;
                editor.focus();
                editor.selection.moveToBookmark(bm);
            }

            const getMenuItems = function () {
                return [
                    {
                        type: "menuitem",
                        text: strings.LOWERCASE,
                        //onAction: lowerCase()
                        onAction: () => apply(strings.LOWERCASE)
                    },
                    {
                        type: "menuitem",
                        text: strings.UPPERCASE,
                        //onAction: upperCase()
                        onAction: () => apply(strings.UPPERCASE)
                    },
                    {
                        type: "menuitem",
                        text: strings.SENTENCECASE,
                        //onAction: sentenceCase()
                        onAction: () => apply(strings.SENTENCECASE)
                    },
                    {
                        type: "menuitem",
                        text: strings.TITLECASE,
                        //onAction: titleCase()
                        onAction: () => apply(strings.TITLECASE)
                    }
                ]
            }

            const getMenuButton = function () {
                return {
                    icon: 'change-case',
                    tooltip: strings.TOOLNAME,
                    fetch: function (callback) {
                        const items = getMenuItems();
                        callback(items);
                    }
                }
            }

            const getNestedMenuItem = function () {
                return {
                    text: strings.TOOLNAME,
                    getSubmenuItems: () => {
                        return getMenuItems();
                    }
                }
            }

            editor.ui.registry.addMenuButton('case', getMenuButton());
            editor.ui.registry.addNestedMenuItem('case', getNestedMenuItem());

            editor.addCommand('mceLowerCase', () => apply(strings.LOWERCASE));
            editor.addCommand('mceUpperCase', () => apply(strings.UPPERCASE));
            editor.addCommand('mceSentenceCase', () => apply(strings.SENTENCECASE));
            editor.addCommand('mceTitleCase', () => apply(strings.TITLECASE));

            return {
                getMetadata: function () {
                    return {
                        name: "Case",
                        url: "https://github.com/melquibrito/Case-change-tinymce-plugin"
                    }
                }
            }
        }
    );
})();
