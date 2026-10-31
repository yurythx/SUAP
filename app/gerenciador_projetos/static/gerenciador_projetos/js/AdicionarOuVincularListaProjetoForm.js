$(document).ready(function() {
    $(".form-row.lista").hide();
    $('input:radio[name=acao]').change(function() {
       if ($(this).val() === 'V'){
            $(".form-row.lista").show();
            $(".form-row.titulo").hide();
        } else {
            $(".form-row.lista").hide();
            $(".form-row.titulo").show();
        }
    });

});
