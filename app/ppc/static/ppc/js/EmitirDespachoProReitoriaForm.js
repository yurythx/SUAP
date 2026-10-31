
function checar_rejeitado_proreitoria() {

    if (document.getElementById('id_rejeitado_proreitoria').checked) {
        $('#id_ad_referendum').parent().parent().hide();
        $('#id_ad_referendum').prop('checked', false);
        $('#id_pular_camara').parent().parent().hide();
        $('#id_pular_camara').prop('checked', false);
        if ($('.camara').length > 0) {
            $('.camara').hide();
        }
    } else {
        $('#id_ad_referendum').parent().parent().show();
        if ($('.camara').length > 0) {
            $('.camara').show();
        }
    }
}

function checar_ad_referendum() {

    if (document.getElementById('id_ad_referendum').checked) {
        $('#id_pular_camara').parent().parent().show();
    } else {
        $('#id_pular_camara').parent().parent().hide();
        $('#id_pular_camara').prop('checked', false);
    }
}

jQuery(function () {


    if ($('#id_rejeitado_proreitoria').length > 0) {
        $('#id_rejeitado_proreitoria').click(function () {
            checar_rejeitado_proreitoria();
        });
        
        checar_rejeitado_proreitoria();
    }

    $('#id_ad_referendum').click(function () {
        checar_ad_referendum();
    });
    
    checar_ad_referendum();
});
