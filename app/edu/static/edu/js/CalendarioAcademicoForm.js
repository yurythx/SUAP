function checar_etapa(n, checado){
    if (checado) {
        $('#id_data_inicio_etapa_'+n).parent().parent().parent().show();
    } else {
        $('#id_data_inicio_etapa_'+n).parent().parent().parent().hide();
        $('#id_data_inicio_etapa_'+n).val('');
        $('#id_data_fim_etapa_'+n).val('');
    }
}
function checar_etapas() {
    if(document.getElementById('id_qtd_etapas_0').checked){
        checar_etapa(1, true);
        checar_etapa(2, false);
        checar_etapa(3, false);
        checar_etapa(4, false);
    } else if(document.getElementById('id_qtd_etapas_1').checked){
        checar_etapa(1, true);
        checar_etapa(2, true);
        checar_etapa(3, false);
        checar_etapa(4, false);
    } else if(document.getElementById('id_qtd_etapas_2').checked){
        checar_etapa(1, true);
        checar_etapa(2, true);
        checar_etapa(3, true);
        checar_etapa(4, false);
    } else if(document.getElementById('id_qtd_etapas_3').checked){
        checar_etapa(1, true);
        checar_etapa(2, true);
        checar_etapa(3, true);
        checar_etapa(4, true);
    }
}

function checar_datas() {
    const checkbox = $('#id_eh_calendario_referencia');
    const d1 = $('#id_data_inicio_trancamento2').parent().parent();
    const d2 = $('#data_fim_trancamento2').parent().parent();
    const d3 = $('#id_data_inicio_certificacao2').parent().parent();
    const d4 = $('#id_data_fim_certificacao2').parent().parent();
    if(checkbox.is(':checked')){
        d1.show();
        d2.show();
        d3.show();
        d4.show();
    } else {
        d1.hide();
        d2.hide();
        d3.hide();
        d4.hide();
    }
}

jQuery(function () {
    $('#id_eh_calendario_referencia').click(function () {
        checar_datas();
    });
    $('#id_qtd_etapas_0').click(function () {
        checar_etapas();
    });
    $('#id_qtd_etapas_1').click(function () {
        checar_etapas();
    });
    $('#id_qtd_etapas_2').click(function () {
        checar_etapas();
    });
    $('#id_qtd_etapas_3').click(function () {
        checar_etapas();
    });
    checar_datas();
    checar_etapas();
});
