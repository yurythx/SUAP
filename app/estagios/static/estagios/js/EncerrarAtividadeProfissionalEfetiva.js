function configurar_form(){
    var conclusao = $('input[name="conclusao"]')

    if(conclusao[0].checked){
        esconder();
    } else{
        exibir();
    }
}

function exibir(){
    $( "fieldset" ).last().show();
}
function esconder(){
    $( "fieldset" ).last().hide();
}
jQuery(document).ready(function(){
    configurar_form();
    $('input[name="conclusao"]').change(function(){configurar_form();});
});
