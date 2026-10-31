function checar_area_e_eixo() {
    var modalidade_id = $('[id^="modalidade_"]').val();
    if (modalidade_id) {
        var eixo = $('[id^="eixo_"]');
        var curso_tecnico = $('[id^="curso_tecnico_"]');
        var area_capes = $('[id^="area_capes_"]');
        var area = $('[id^="area_"]:not([id*="_capes_"]):not([id*="_concentracao_"]):not([id*="_curso_formacao_superior_"])');
        var area_curso_superior = $('[id^="area_curso_formacao_superior_"]');
        if (modalidade_id == 2 || modalidade_id == 23 || modalidade_id == 4 || modalidade_id == 14 || modalidade_id == 19) {
            area_curso_superior.parent().parent().show();
        }else{
            area_curso_superior.parent().parent().hide();
            area_curso_superior.val(null);
        }

        if (modalidade_id == 14 || modalidade_id == 8 || modalidade_id == 11 || modalidade_id == 12 || modalidade_id == 18 || modalidade_id == 13) {
            //Curso tecnológicos ou FIC
            eixo.parent().parent().show();
            area_capes.parent().parent().hide();
            area_capes.val(null);
            area_capes.next().children().children().children().text('')
            area.parent().parent().hide();
            area.val(null);
            area.next().children().children().children().text('')
            if (modalidade_id == 18 || modalidade_id == 13) {
                curso_tecnico.parent().parent().show();
            }
        } else if (modalidade_id == 9 || modalidade_id == 10 || modalidade_id == 16) {
            area_capes.parent().parent().show();
            area.parent().parent().hide();
            area.val(null);
            area.next().children().children().children().text('')
            eixo.parent().parent().hide();
            eixo.val(null);
            eixo.next().children().children().children().text('')
            curso_tecnico.parent().parent().hide();
            curso_tecnico.val(null);
            curso_tecnico.next().children().children().children().text('')
        } else {
            area.parent().parent().show();
            area_capes.parent().parent().hide();
            area_capes.val(null);
            area_capes.next().children().children().children().text('')
            eixo.parent().parent().hide();
            eixo.val(null);
            eixo.next().children().children().children().text('')
            curso_tecnico.parent().parent().hide();
            curso_tecnico.val(null);
            curso_tecnico.next().children().children().children().text('')
        }
    }
}

function checar_descricao() {
    $('#id_descricao_historico').val($('#id_descricao').val());
}

function checar_mesmo_curso() {
    var mesmo_curso_id = $('[id^="mesmo_curso_"]').val();
    var modalidade = $('[id^="modalidade_"]')
    var eixo = $('[id^="eixo_"]');
    var curso_tecnico = $('[id^="curso_tecnico_"]');
    var area_capes = $('[id^="area_capes_"]');
    var area = $('[id^="area_"]:not([id*="_capes_"]):not([id*="_concentracao_"])');
    var diretoria = $('[id^="diretoria_"]');
    if(mesmo_curso_id){
        $('#id_data_inicio').parent().parent().parent().hide();
        $('#id_codigo_censup').parent().parent().hide();
        $('#id_codigo_sistec').parent().parent().hide();
        $('#id_ciencia_sem_fronteira').parent().parent().hide();
        $('#id_numero_portaria_coordenador').parent().parent().parent().hide();
        modalidade.parent().parent().parent().hide();
        eixo.parent().parent().parent().hide();
        curso_tecnico.parent().parent().parent().hide();
        area_capes.parent().parent().parent().hide();
        area.parent().parent().parent().hide();
        $('#id_periodicidade').parent().parent().hide();
        diretoria.parent().parent().parent().hide();
    }else{
        $('#id_data_inicio').parent().parent().parent().show();
        $('#id_codigo_censup').parent().parent().show();
        $('#id_codigo_sistec').parent().parent().show();
        $('#id_ciencia_sem_fronteira').parent().parent().show();
        $('#id_numero_portaria_coordenador').parent().parent().parent().show();
        modalidade.parent().parent().parent().show();
        eixo.parent().parent().parent().show();
        curso_tecnico.parent().parent().parent().show();
        area_capes.parent().parent().parent().show();
        area.parent().parent().parent().show();
        $('#id_periodicidade').parent().parent().show();
        diretoria.parent().parent().parent().show();
    }
}

jQuery(function () {
    var modalidade = $('[id^="modalidade_"]');

    modalidade.change(function () {
        checar_area_e_eixo();
    });

    $('#id_descricao').keyup(function () {
        checar_descricao();
    });

    var mesmo_curso = $('[id^="mesmo_curso_"]');

    mesmo_curso.change(function () {
        checar_mesmo_curso();
    });

    checar_mesmo_curso();

});
