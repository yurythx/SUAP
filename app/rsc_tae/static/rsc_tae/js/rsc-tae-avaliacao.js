(() => {
    document.addEventListener('click', (ev) => {
        const btn = ev.target.closest('.js-av-validar-anexo');
        if (!btn) return;

        const container = btn.closest('.js-av-anexo');
        if (!container) return;

        const status = container.querySelector('.js-av-anexo-status');
        const validadoAtual = container.dataset.validado === '1';
        const validadoNovo = !validadoAtual;
        container.dataset.validado = validadoNovo ? '1' : '0';

        if (status) {
            status.textContent = validadoNovo ? 'Validado' : 'Pendente';
            status.classList.toggle('success', validadoNovo);
            status.classList.toggle('default', !validadoNovo);
        }

        btn.classList.toggle('default', validadoNovo);
        btn.classList.toggle('success', !validadoNovo);
        btn.title = validadoNovo ? 'Desfazer validação' : 'Validar';
        btn.setAttribute('aria-label', btn.title);
        btn.innerHTML = validadoNovo
            ? '<span class="icone fas fa-undo" aria-hidden="true"></span><span class="rsc-btn-label">Desfazer</span>'
            : '<span class="icone fas fa-check" aria-hidden="true"></span><span class="rsc-btn-label">Validar</span>';
    });
})();
