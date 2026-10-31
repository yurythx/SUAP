joint.shapes.custom = {};
joint.shapes.custom.PeriodElement = joint.shapes.basic.Rect.extend({
    markup: '<g class="rotatable"><g class="scalable"><rect/></g><text/></g>',
    defaults: joint.util.deepSupplement({
        type: 'custom.PeriodElement'
    }, joint.shapes.basic.Rect.prototype.defaults)
});

function format(str) {
    var result = '';
    while (str.length > 0) {
        var position = str.substring(0, 25).lastIndexOf(' ');
        if (position < 20)
            position = 25;
        result += str.substring(0, position) + '\n';
        str = str.substring(position);
    }
    if (result.length > 100) {
        result = result.substring(0, 95) + '...';
    }
    return result;
}

// The following custom shape creates a link out of the whole element.
joint.shapes.custom.ElementLink = joint.shapes.basic.Generic.extend({
    // Note the `<a>` SVG element surrounding the rest of the markup.
    markup: [
        '<a onclick="javascript:popup(this.href.baseVal, 800, 300); return false;" title="ElementLink">',
        '<g class="rotatable">',
        '<g class="scalable">',
        '<rect class="acronym-rect"/><rect class="name-rect"/><rect class="hour-rect"/>',
        '</g>',
        '<text class="acronym-text"/><text class="name-text"/><text class="hour-text"/>',
        '</g>',
        '</a>'
    ].join(''),
    defaults: joint.util.deepSupplement({

        type: 'custom.ElementLink',

        attrs: {
            rect: {
                'width': 200
            },

            '.acronym-rect': {
                'stroke': 'black',
                'stroke-width': 2,
                'fill': '#fff'
            },
            '.name-rect': {
                'stroke': 'black',
                'stroke-width': 2,
                'fill': '#fff'
            },
            '.hour-rect': {
                'stroke': 'black',
                'stroke-width': 2,
                'fill': '#fff'
            },

            '.acronym-text': {
                'ref': '.acronym-rect',
                'ref-y': .85,
                'ref-x': .07,
                'text-anchor': 'start',
                'y-alignment': 'middle',
                'font-family': 'Lato, Arial, sans-serif',
                'fill': 'black',
                'font-size': 11
            },
            '.name-text': {
                'ref': '.name-rect',
                'ref-y': .5,
                'ref-x': .5,
                'text-anchor': 'middle',
                'y-alignment': 'middle',
                'fill': 'black',
                'font-size': 11,
                'height': '30px',
                'font-family': 'Lato, Arial, sans-serif',
                'font-weight': 'bold'
            },
            '.hour-text': {
                'ref': '.hour-rect',
                'ref-y': .8,
                'ref-x': .9,
                'text-anchor': 'end',
                'y-alignment': 'middle',
                'font-family': 'Lato, Arial, sans-serif',
                'fill': 'black',
                'font-size': 11
            }
        },

        acronym: [],
        name: [],
        hour: []

    }, joint.shapes.basic.Generic.prototype.defaults),

    initialize: function () {

        _.bindAll(this, 'updateRectangles');

        this.on('change:acronym change:name change:hour', function () {
            this.updateRectangles();
            this.trigger('uml-update');
        });

        this.updateRectangles();

        joint.shapes.basic.Generic.prototype.initialize.apply(this, arguments);
    },

    getName: function () {
        return this.get('name');
    },

    updateRectangles: function () {

        var attrs = this.get('attrs');

        var rects = [{
            type: 'acronym',
            text: this.get('acronym'),
            height: 80
        }, {
            type: 'name',
            text: this.getName(),
            height: 240
        }, {
            type: 'hour',
            text: this.get('hour') + 'h',
            height: 80
        }];

        var offsetY = 0;

        _.each(rects, function (rect) {

            var lines = (_.isArray(rect.text) ? rect.text : [rect.text]).join('\n');
            attrs['.' + rect.type + '-text'].text = format(lines);
            attrs['.' + rect.type + '-rect'].height = rect.height;
            attrs['.' + rect.type + '-rect'].transform = 'translate(0,' + offsetY + ')';

            offsetY += rect.height;
        });
    }
});

function draw_rectangle(textJSON, num_max_comp_periodo, num_periodos) {
    var obj = JSON.parse(textJSON);
    var tem_optativos = false;
    for (var i = 0; i < obj.matriz.length; i++) {
        if (obj.matriz[i].optativo) {
            tem_optativos = true;
            break;
        }
    }

    function makeElement(x, y, width, height, acronym, name, hour, pk) {
        var r = new joint.shapes.custom.ElementLink({
            id: pk,
            position: {
                x: x,
                y: y
            },
            size: {
                width: width,
                height: height
            },
            acronym: acronym,
            name: [name],
            hour: [hour],
            attrs: {
                a: {
                    'xlink:href': "/edu/definir_requisitos/" + pk + "/",
                    'xlink:show': 'new',
                    cursor: 'pointer'
                }
            }
        });
        graph.addCell(r);
        return r;
    };

    function makePeriod(x, y, width, height, label, pk, background, font_weight) {
        var letterSize = 11;
        var r = new joint.shapes.custom.PeriodElement({
            id: pk,
            position: {
                x: x,
                y: y
            },
            size: {
                width: width,
                height: height
            },
            attrs: {
                rect: {
                    fill: background
                },
                a: {
                    'xlink:href': "/edu/definir_requisitos/" + pk + "/",
                    'xlink:show': 'new',
                    cursor: 'pointer'
                },
                text: {
                    text: label,
                    'font-size': letterSize,
                    'font-weight': font_weight
                }
            }
        });
        graph.addCell(r);
        return r;
    };

    function makeLink(pk_source, pk_target, is_pre) {
        var mylink = new joint.dia.Link({
            source: {
                id: pk_source
            },
            target: {
                id: pk_target
            }
        });

        mylink.attr({
            '.connection': {
                stroke: 'black'
            },
            '.marker-source': {
                fill: 'black',
                d: 'M 10 0 L 0 5 L 10 10 z'
            }
        });
        if (!is_pre) {
            mylink.attr({
                '.connection': {
                    'stroke-dasharray': '5 2'
                }
            });
        }
        mylink.set('router', {
            name: 'manhattan'
        });
        //manhattan, metro and orthogonal
        mylink.set('connector', {
            name: 'normal'
        });
        //normal, smooth and rounded
        graph.addCell(mylink);
        return mylink;
    }

    if (tem_optativos)
        num_periodos = parseInt(num_periodos) + 1;
    //Configuração inicial do graph do jointjs
    var graph = new joint.dia.Graph;
    new joint.dia.Paper({
        el: $('#matriz'),
        width: num_periodos * 200,
        height: num_max_comp_periodo * 150,
        gridSize: 1,
        model: graph,
        perpendicularLinks: true,
        interactive: false
    });

    var height = 100;
    var h_spacing = 40;
    var h = 50;

    var width = 150;
    var w_spacing = 50;
    var w = 30;

    //cria os retângulos
    var i;
    var periodo = '1';
    makePeriod(w, 1, width, 20, periodo + 'º período', periodo + 'p', 'white', 'bold');
    for (i = 0; i < obj.matriz.length; i++) {
        if (obj.matriz[i].periodo != periodo) {
            periodo = obj.matriz[i].periodo;
            var h = 50;
            var w = w + width + w_spacing;
            if (periodo != 0)
                makePeriod(w, 0, width, 20, periodo + 'º período', periodo + 'p', 'white', 'bold');
            else
                makePeriod(w, 0, width, 20, 'Optativos', periodo + 'p', 'white', 'bold');
        }

        var background = 'white';
        switch (obj.matriz[i].tipo) {
            case '1':
                //regular optativo
                background = 'white';
                break;
            case '2':
                //regular obrigatório
                background = 'white';
                break;
            case '3':
                //regular obrigatório
                background = 'white';
                break;
        }

        makeElement(w, h, width, height, obj.matriz[i].sigla, obj.matriz[i].componente, obj.matriz[i].ch_hora_relogio, obj.matriz[i].id, background, 'normal');
        var h = h + height + h_spacing;
    }

    //cria os relacionamentos
    var j;
    for (i = 0; i < obj.matriz.length; i++) {
        for (j = 0; j < obj.matriz[i].prerequisitos.length; j++) {
            makeLink(obj.matriz[i].id, obj.matriz[i].prerequisitos[j].id, true);
        }
        for (j = 0; j < obj.matriz[i].corequisitos.length; j++) {
            makeLink(obj.matriz[i].id, obj.matriz[i].corequisitos[j].id, false);
        }
    }
}
