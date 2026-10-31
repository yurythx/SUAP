function slugify(text) {
    return text
        .toString()
        .normalize('NFD')                   // separa acentos
        .replace(/[\u0300-\u036f]/g, '')    // remove acentos
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, '-')        // qualquer coisa não alfanumérica -> "-"
        .replace(/^-+|-+$/g, '');           // tira "-" do início/fim
}

function initAutoSlugFields() {
    // Todo campo que tiver data-slug-target-id será considerado "origem"
    const slugSources = document.querySelectorAll('[data-slug-target-id]');

    slugSources.forEach(function (source) {
        const targetId = source.getAttribute('data-slug-target-id');
        const target = document.getElementById(targetId);

        if (!target) {
            return;
        }

        // Por padrão, deixa o campo alvo somente leitura
        if (!target.hasAttribute('data-slug-editable')) {
            target.readOnly = true;
        }

        source.addEventListener('input', function () {
            target.value = slugify(source.value);
        });
    });
}

document.addEventListener('DOMContentLoaded', initAutoSlugFields);
