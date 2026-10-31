__filter_pks = function(form_parameter){
    let vetor = $.parseJSON(form_parameter);
    let vetor_pks = {};
    vetor.forEach(function(filter){
        let seletor_input = $("input[name$="+filter[0].toString()+"]");
        let seletor_select = $("seletor_select[name$="+filter[0].toString()+"]");
        let select = $("select[name$="+filter[0].toString()+"]");
        if(
            seletor_input.length === 2){
            vetor_pks[filter[1]] = $("#hidden_"+filter[0].toString()).val().toString();
        }
        if(seletor_input.length === 1){
            vetor_pks[filter[1]] = seletor_input.val().toString();
        }
        if(seletor_select.length === 1) {
            vetor_pks[filter[1]] = seletor_select.val().toString();
        }
        if(select.length === 1 && select.val()) {
            vetor_pks[filter[1]] = select.val().toString();
        }
    });
    return JSON.stringify(vetor_pks);
};
