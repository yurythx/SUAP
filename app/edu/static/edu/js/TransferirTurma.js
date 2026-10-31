function popupTransferencia(turma) {
    var inputs = $("input[name='matriculas_periodo']");
    var pks = [];
    for (u = 0; u < inputs.length; u++) {
        if (inputs[u].checked) {
            pks.push(inputs[u].value);
        }
    }

    pks = pks.join("_");
    if (pks.length > 0) {
        pks = pks + "/";
    }

    if (pks.length == 0) {
        alert('Por favor, selecione o(s) aluno(s) que deseja transferir.');
    }
    else {
        document.location.href = "/edu/transferir_turma/" + turma + "/" + pks;
    }
}
