document.addEventListener("DOMContentLoaded", function () {
    const $cat = document.getElementById('id_categoria');

    // inputs
    const $ini = document.getElementById('id_data_inicio');
    const $fim = document.getElementById('id_data_fim');
    const $dia = document.getElementById('id_dia_recorrente');
    const $mes = document.getElementById('id_mes_recorrente');

    // fieldsets (pais) — usa os inputs para localizar o fieldset.module
    const $fsPontual = $ini ? $ini.closest('fieldset.module') : null;        // "Ocorrência Pontual"
    const $fsRecorrente = $dia ? $dia.closest('fieldset.module') : null;        // "Ocorrência Recorrente"

    // mapeamento da enum CategoriaLiberacao
    const CATEGORIA = { FERIADO: 1, FERIADO_RECORRENTE: 2, RECESSO: 3 };

    // mostra/esconde um fieldset e habilita/desabilita todos os campos dentro
    function setFieldsetVisible(fs, visible) {
        if (!fs) return;
        fs.style.display = visible ? '' : 'none';
        fs.querySelectorAll('input, select, textarea, button').forEach(el => {
            el.disabled = !visible;
        });
    }

    // controla required/disabled de campos específicos (sem apagar valores)
    function setFieldActive(input, active, required = false) {
        if (!input) return;
        input.disabled = !active;
        input.required = !!(active && required);
    }

    function updateVisibility() {
        const v = parseInt(($cat && $cat.value) || 0, 10);
        const isRecorrente = v === CATEGORIA.FERIADO_RECORRENTE;
        const isPontual = v === CATEGORIA.FERIADO || v === CATEGORIA.RECESSO;

        // Fieldsets
        setFieldsetVisible($fsPontual, isPontual);
        setFieldsetVisible($fsRecorrente, isRecorrente);

        // Regras de required/disabled nos campos principais
        setFieldActive($ini, isPontual, true);      // pontual: data_inicio obrigatório
        setFieldActive($fim, isPontual, false);     // data_fim opcional
        setFieldActive($dia, isRecorrente, true);   // recorrente: dia obrigatório
        setFieldActive($mes, isRecorrente, true);   // recorrente: mês obrigatório
    }

    if ($cat) $cat.addEventListener('change', updateVisibility);
    updateVisibility();
});
