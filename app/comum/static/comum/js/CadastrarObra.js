$(function() {
    $("#id_tipo").on("change", function(e){

        var tipo = $(this).val()
        var TIPO_REFORMA = 2

        if(tipo == TIPO_REFORMA) {
            $(".field-area_construida").hide()
        }else {
            $(".field-area_construida").show()
        }

    });
});
