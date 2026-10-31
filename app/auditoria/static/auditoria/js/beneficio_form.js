document.addEventListener("DOMContentLoaded", function () {
    // Obtém os campos do formulário
    const origemBeneficioField = document.getElementById("id_origem_beneficio");
    const origemTrabalhoField = document.getElementById("id_servico_auditoria");
    const origemOutrosField = document.getElementById("id_servico_auditoria_outros");
    const monitoramentoField = document.getElementById("id_monitoramento");
    const tipoBeneficioField = document.getElementById("id_tipo");
    const metodologiaCalculoField = document.getElementById("id_metodologia_calculo");

    const financeiroFields = ["id_valor_beneficio", "id_responsavel_calculo", "id_metodologia_calculo"];
    const qualitativoFields = ["id_unidade_afetada", "id_alcance_estrategico"];

    // Função auxiliar para mostrar/ocultar campos
    function toggleFieldVisibility(fieldId, show) {
        const fieldElement = document.getElementById(fieldId);
        if (fieldElement) {
            fieldElement.closest(".form-group, .form-row, p").style.display = show ? "" : "none";
        }
    }
    function toggleFieldVisibilityByForId(forId, show) {
        const label = document.querySelector(`label[for="${forId}"]`);
        if (label) {
            label.closest(".form-group, .form-row, p").style.display = show ? "" : "none";
        }
    }
    // Função para mostrar ou esconder os campos relacionados à origem do benefício
    function toggleOrigemBeneficioFields() {
        if (!origemBeneficioField) return;

        const valor = origemBeneficioField.value;
        if (valor === "1") { // 1 = Recomendação
            toggleFieldVisibility("id_monitoramento", true);
        } else {
            toggleFieldVisibility("id_monitoramento", false);
            if (monitoramentoField) monitoramentoField.value = "";
        }
    }

    // Função para mostrar ou esconder o campo "Descrição de Outros"
    function toggleOrigemTrabalhoFields() {
        if (!origemTrabalhoField || !origemOutrosField) return;

        const selectedOption = origemTrabalhoField.options[origemTrabalhoField.selectedIndex]?.text;
        if (selectedOption === "Outros") {
            toggleFieldVisibility("id_servico_auditoria_outros", true);
        } else {
            toggleFieldVisibility("id_servico_auditoria_outros", false);
            origemOutrosField.value = "";
        }
    }

    // Função para ocultar/mostrar campos dependendo do tipo de benefício
    function toggleTipoBeneficioField() {
        if (!tipoBeneficioField) return;

        const tipo = tipoBeneficioField.value;

        // Esconde todos os campos primeiro
        financeiroFields.forEach(id => toggleFieldVisibility(id, false));
        qualitativoFields.forEach(id => toggleFieldVisibilityByForId(id, false));

        // Mostra apenas os campos correspondentes ao tipo selecionado
        if (tipo === "1") {  // Tipo Financeiro
            financeiroFields.forEach(id => toggleFieldVisibility(id, true));
        } else if (tipo === "2") {  // Tipo Qualitativo
            qualitativoFields.forEach(id => toggleFieldVisibilityByForId(id, true));
        }
    }

    // Adiciona eventos aos campos
    if (tipoBeneficioField) tipoBeneficioField.addEventListener("change", toggleTipoBeneficioField);
    if (origemBeneficioField) origemBeneficioField.addEventListener("change", toggleOrigemBeneficioFields);
    if (origemTrabalhoField) origemTrabalhoField.addEventListener("change", toggleOrigemTrabalhoFields);

    // Executa as funções no carregamento inicial
    toggleOrigemBeneficioFields();
    toggleOrigemTrabalhoFields();
    toggleTipoBeneficioField();
});
