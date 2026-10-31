/**
 * Copyright (c) 2016, LOVATA - Aleksandra Shinkevich (a.shinkevich@lovata.com). All rights reserved.
 * For licensing, see LICENSE.md
 *
 * A simple ruler plugin for CKEditor (http://ckeditor.com)
 *
 * Require:
 * - nouislider (github.com/leongersen/noUiSlider) for ranging
 * - jquery (github.com/jquery/jquery) for DOM traversing
 */


// if (!window.$) {
//     window.$ = require('jquery');
//     window.noUiSlider = require('nouislider');
// }

var count = 0;

CKEDITOR.plugins.add("simple-ruler", {
    init: function(editor) {
        var width = 800;
        var configs = getConfigs(editor.config.ruler);
        var mode = 'wysiwyg';
        editor.addContentsCss(this.path + 'styles/editor-iframe-styles.css');
        editor.on('instanceReady', onInit);

        editor.on('change', function(evt) {
            setPadding();

        });
        editor.on('setRulerPadding', function(evt) {
            local_count = editor.id.match(/\d+/)[0];
            var id_div = 'cke_ruler_wrap'+ local_count;
            setPadding([evt.data.left, evt.data.right]);
            var range = document.getElementById(id_div);
            range.noUiSlider.set([evt.data.left, evt.data.right]);
            
        });
        // Fix ruler's fail after switching from source to wysiwyg mode
        editor.on('mode', function() {
            if (mode !== editor.mode && editor.mode === 'wysiwyg') {
                onInit();
            } else {
                mode = editor.mode;
            }
        });
        function onInit() {
            count += 1;
            var id_div = 'cke_ruler_wrap' + count;
            var $ckeContent = $(editor.element.$).siblings('.cke').find('.cke_contents');
            $ckeContent.prepend('<div id="' + id_div + '"></div>');
            var range = document.getElementById(id_div);
            var suap_ckeditor = null;
            var elements = editor.document.getBody().getElementsByTag( '*' );
            for ( var i = 0; i < elements.count(); ++i )
            {
                var element = elements.getItem(i);
                if(element.getId() == "suap-ckeditor")
                {
                    suap_ckeditor = element;
                    break;
                }
            }
            if (suap_ckeditor)
            {
                configs.sliders.left = suap_ckeditor.getAttribute("data-left");
                configs.sliders.right = suap_ckeditor.getAttribute("data-right");
                editor.setData(suap_ckeditor.getHtml());
            }

            setPadding([configs.sliders.left, configs.sliders.right]);
            noUiSlider.create(range, {
                start: [configs.sliders.left, configs.sliders.right],
                margin: 2,
                connect: [true, false, true],
                behaviour: 'drag',
                step: configs.step,
                range: {
                    'min': 0,
                    'max': configs.values
                },
                pips: {
                    mode: 'count',
                    values: configs.values,
                    density: 2
                }
            });


            // html_content  = editor.document.getBody().getHtml();
            // var suap_div = $('#suap-ckeditor').html();
            // console.log(html_content);
            // div.parentNode.removeChild(suap_div);
            // $('#suap-ckeditor').remove();
            // console.log(suap_div);
            // var suap_div = null;
            // var elements = editor.document.getBody().getElementsByTag( '*' );
            // for ( var i = 0; i < elements.count(); ++i ) {
            //     var element = elements.getItem(i);
            //     if(element.getId() == "suap-ckeditor")
            //         console.log(element.innerHTML);
            // }
            // if(suap_div == null) {
            //     console.log("Setting ");
            //     html_content  = editor.document.getBody().getHtml();
            //     html_content = "<div id='suap-ckeditor'>" + html_content  + "</div>";
            //     editor.setData(html_content);
            //
            // }
            // When the input changes, set the slider value
            // valueInput.addEventListener('change', function () {
            //     range.noUiSlider.set([null, this.value]);
            // });
            range.noUiSlider.on('change', function (values) {
                setPadding(values);
            });
        }
        function setPadding(values) {
            if (values) {
                configs.sliders.left = parseFloat(values[0]);
                configs.sliders.right = parseFloat(values[1]);
            }
            var left = (width / configs.values) * configs.sliders.left;
            var right = (width / configs.values) * (configs.values - configs.sliders.right);
            editor.document.getBody().setStyle('padding', configs.padding.top + 'px ' + right + 'px ' + configs.padding.bottom + 'px ' + left + 'px');
            //
            var local_count = editor.id.match(/\d+/)[0];
            var id_div = 'cke_ruler_wrap' + local_count;
            var valueInput = document.getElementById(id_div);
            if (valueInput)
            {
                valueInput.setAttribute('padding', configs.padding.top + 'px ' + right + 'px ' + configs.padding.bottom + 'px ' + left + 'px');
                valueInput.setAttribute('data-left', configs.sliders.left);
                valueInput.setAttribute('data-right', configs.sliders.right);
            }

            //
            // var elements = editor.document.getBody().getElementsByTag( '*' );
            // for ( var i = 0; i < elements.count(); ++i )
            // {
            //     var element = elements.getItem(i);
            //     element.setAttribute('padding', configs.padding.top + 'px ' + right + 'px ' + configs.padding.bottom + 'px ' + left + 'px');
            //     console.log( element.getName());
            // }
            editor.fire('updateRuler', configs.sliders);
        }

        function getConfigs(config) {
            var defaultConfig = {
                values: 21, // segment number of the ruler
                step: 0.25, // accuracy of sliders
                sliders: {
                    left: 2, // left slider value
                    right: 19 // right slider value (21-19 = 2)
                },
                padding: {
                    top: 20, // top 'canvas' padding (px)
                    bottom: 20 // bottom 'canvas' padding (px)
                }
            };
            if (!config)
            {
                // Oops, no configs
                config = defaultConfig;
            }
            else
            {
                if (!config.sliders)
                {
                    // Oops, no sliders info
                    config.sliders = defaultConfig.sliders;
                }
                else
                {
                    if (!config.sliders.hasOwnProperty('left')) {
                        config.sliders.left = defaultConfig.sliders.left;
                    }
                    if (!config.sliders.hasOwnProperty('right')) {
                        config.sliders.right = defaultConfig.sliders.right;
                    }
                }
                if (!config.padding) {
                    // Oops, no padding info
                    config.padding = defaultConfig.padding;
                } else {
                    if (!config.padding.hasOwnProperty('top')) {
                        config.padding.top = defaultConfig.padding.top;
                    }
                    if (!config.padding.hasOwnProperty('bottom')) {
                        config.padding.bottom = defaultConfig.padding.bottom;
                    }
                }
                if (!config.hasOwnProperty('values')) {
                    // Oops, no values info
                    config.values = defaultConfig.values;
                } else if (config.values < config.sliders.right) {
                    // Oops, values is less then right slider value
                    config.values = config.sliders.right;
                }
                if (!config.hasOwnProperty('step')) {
                    // Oops, no step info
                    config.step = defaultConfig.step;
                }
            }
            return config;
        }
    }
});
