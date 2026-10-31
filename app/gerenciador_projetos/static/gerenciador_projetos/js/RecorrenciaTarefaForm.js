$( document ).ready(function() {

    function atualiza_selects(id_tipo_recorrencia) {
        if (id_tipo_recorrencia === '2'){
            $(".form-row.dia_da_semana").show();
            $(".form-row.dia_do_mes").hide();
            $(".form-row.mes_do_ano").hide();
        } else if (id_tipo_recorrencia === '3'){
            $(".form-row.dia_da_semana").hide();
            $(".form-row.dia_do_mes").show();
            $(".form-row.mes_do_ano").hide();
        } else if (id_tipo_recorrencia === '4'){
            $(".form-row.dia_da_semana").hide();
            $(".form-row.dia_do_mes").show();
            $(".form-row.mes_do_ano").show();
        } else {
            $(".form-row.dia_da_semana").hide();
            $(".form-row.dia_do_mes").hide();
            $(".form-row.mes_do_ano").hide();
        }
    }

    id_tipo_recorrencia = $('select#id_tipo_recorrencia').val();
    atualiza_selects(id_tipo_recorrencia);
    $('select#id_tipo_recorrencia').on('change', function(){
        id_tipo_recorrencia = $(this).val();
        atualiza_selects(id_tipo_recorrencia);
    });

});
