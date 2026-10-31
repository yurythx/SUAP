function configurar_form(){
    var tipos = $('input[name="tipos_aditivo"]');
    
    if(tipos[0].checked){
        exibir("label[for='id_orientador']");
    } else{
        esconder("label[for='id_orientador']");
    }

    if(tipos[1].checked){
        exibir('#id_remunerada');
        exibir('#id_tipo_remuneracao');
        exibir('#id_valor');
    } else{
        esconder('#id_remunerada');
        esconder('#id_tipo_remuneracao');
        esconder('#id_valor');
    }

    if(tipos[2].checked){
        exibir('#id_auxilio_transporte');
    } else {
        esconder('#id_auxilio_transporte');
    }

    if(tipos[3].checked){
        exibir('#id_auxilio_alimentacao');
    } else {
        esconder('#id_auxilio_alimentacao');
    }

    if(tipos[4].checked){
        exibir('#id_data_prevista_fim');
    } else {
        esconder('#id_data_prevista_fim');
    }

    if(tipos[5].checked){
        exibir('#id_ch_semanal');
    } else {
        esconder('#id_ch_semanal');
    }

    if(tipos[6].checked){
        exibir('#id_plano_atividades');
    } else {
        esconder('#id_plano_atividades');
    }

    if(tipos[7].checked){
        exibir('#id_nome_supervisor');
        exibir('#id_cpf_supervisor');
        exibir('#id_telefone_supervisor');
        exibir('#id_cargo_supervisor');
        exibir('#id_email_supervisor');
        exibir('#id_observacao_supervisor');
    } else {
        esconder('#id_nome_supervisor');
        esconder('#id_cpf_supervisor');
        esconder('#id_telefone_supervisor');
        esconder('#id_cargo_supervisor');
        esconder('#id_email_supervisor');
        esconder('#id_observacao_supervisor');
    }

    if(tipos[8].checked){
        exibir('#id_turno');
    } else {
        esconder('#id_turno');
    }
    if(tipos[9].checked){
        exibir('#id_nome_da_seguradora');
        exibir('#id_numero_seguro');
    } else {
        esconder('#id_nome_da_seguradora');
        esconder('#id_numero_seguro');
    }
}

function exibir(id){
    $(id).closest('fieldset').show();
}
function esconder(id){
    $(id).closest('fieldset').hide();
}
jQuery(document).ready(function(){
    configurar_form();
    $('input[name="tipos_aditivo"]').change(function(){configurar_form();});
});