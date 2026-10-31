function change_hidden_event(selector, callback) {
    var select = $('select[name='+selector+']');
    var oldvalue = select.val();
    setInterval(function () {
        if (select.val() != oldvalue) {
            oldvalue = select.val();
            callback();
        }
    }, 500);
}

function checar_qtd_avaliacoes() {

    if (document.getElementById('id_qtd_avaliacoes').value == 4) {
        $('#id_ch_semanal_1s').parent().parent().show();
    } else {
        $('#id_ch_semanal_1s').parent().parent().hide();
        $('#id_ch_semanal_1s').val('');
        $('#id_ch_semanal_2s').val('');
    }
}

function checar_tipo() {

    if (document.getElementById('id_tipo').value == 5) {
        $('#id_ch_pratica').parent().hide();
        $('#id_ch_pratica').val(0);
        $('#id_ch_pcc').parent().hide();
        $('#id_ch_pcc').val(0);
        $('#id_ch_visita_tecnica').parent().hide();
        $('#id_ch_visita_tecnica').val(0);
        $('#id_ch_extensao').parent().hide();
        $('#id_ch_extensao').val(0);
        $('#id_ch_pratica_decimal').parent().hide();
        $('#id_ch_pratica_decimal').val(0);
        $('#id_ch_pcc_decimal').parent().hide();
        $('#id_ch_pcc_decimal').val(0);
        $('#id_ch_visita_tecnica_decimal').parent().hide();
        $('#id_ch_visita_tecnica_decimal').val(0);
        $('#id_ch_extensao_decimal').parent().hide();
        $('#id_ch_extensao_decimal').val(0);
    } else {
        $('#id_ch_pratica').parent().show();
        $('#id_ch_pcc').parent().show();
        $('#id_ch_visita_tecnica').parent().show();
        $('#id_ch_extensao').parent().show();
        $('#id_ch_pratica_decimal').parent().show();
        $('#id_ch_pcc_decimal').parent().show();
        $('#id_ch_visita_tecnica_decimal').parent().show();
        $('#id_ch_extensao_decimal').parent().show();
    }
}

jQuery(function () {

    var obj = jQuery('#id_is_seminario_estagio_docente');
    obj.on('change', function () {
        var div = jQuery(this).closest('div.is_seminario_estagio_docente').next();
        if (obj.is(':checked')) {
            div.show();
        }else{
            div.find('select').val('');
            div.hide();
        }
    });
    if (!obj.is(':checked')) {
        var div = obj.closest('div.is_seminario_estagio_docente').next();
        div.find('select').val('');
        div.hide()
    }

    var modular = $('#id_tipo_modulo');
    if (modular.is(':hidden')) {
        modular.parent().hide();
    }

    change_hidden_event('componente', function () {
        if ($('select[name=componente]').val() != '') {
            var descricao_componente = $('select[name=componente]').next().children().children().children().html();
            //atribui automaticamente a carga horária presente na descrição do componente ao campo de carga horária teórica'
            jQuery('#id_ch_presencial').val(descricao_componente.split('[')[1].split('/')[0].split(' ')[0]);
            jQuery('#id_ch_presencial_decimal').val(descricao_componente.split('[')[1].split('/')[0].split(' ')[0]);
        } else {
            jQuery('#id_ch_presencial').val(0);
        }
    });

    $('#id_qtd_avaliacoes').click(function () {
        checar_qtd_avaliacoes();
    });

    checar_qtd_avaliacoes();

    $('#id_tipo').click(function () {
        checar_tipo();
    });

    checar_tipo();
});
