$(document).ready(function(){
    $(".form-row.field-cargo_emprego").hide();
    $(".form-row.field-funcao").hide();


    $("#id_papel_0").click(function(){
        $(".form-row.field-cargo_emprego").show();
        $(".form-row.field-funcao").hide();
    })
    $("#id_papel_1").click(function(){
        $(".form-row.field-cargo_emprego").hide();
        $(".form-row.field-funcao").show();
    })
});
