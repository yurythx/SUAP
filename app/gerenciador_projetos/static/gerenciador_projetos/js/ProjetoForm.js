$( document ).ready(function() {
    $(".form-row.field-data_conclusao").hide();
    $('select#id_situacao').on('change', function(){
        if ($(this).val() === '4'){
            $(".form-row.field-data_conclusao").show();
        } else {
            $(".form-row.field-data_conclusao").hide();
        }
    });
});
