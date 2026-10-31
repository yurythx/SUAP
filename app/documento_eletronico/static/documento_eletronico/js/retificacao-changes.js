/**
 * Processa e exibe o resumo de alterações em documentos retificados
 */
(function() {
    'use strict';

    const LABEL_MAP = {
        'adicao': 'Adição',
        'alteracao': 'Alteração',
        'remocao': 'Remoção',
        'adicao_imagem': 'Inclusão de imagem',
        'alteracao_imagem': 'Alteração de imagem',
        'remocao_imagem': 'Remoção de imagem'
    };

    /**
     * Encontra o elemento de dados das mudanças
     */
    function findDataElement() {
        let dataEl = document.getElementById('document-changes-data');
        if (!dataEl) {
            const marqPane = document.getElementById('ver-marq');
            if (marqPane) dataEl = marqPane.querySelector('#document-changes-data');
        }
        return dataEl;
    }

    /**
     * Cria a estrutura de tabela padrão SUAP conforme fornecido
     */
    function createTableWrapper(content) {
        return `
        <div class="table-responsive">
            <table>
                <caption>Resumo de alterações</caption>
                <thead>
                    <tr>
                        <th>Tipo</th>
                        <th>Conteúdo</th>
                    </tr>
                </thead>
                <tbody>
                    ${content}
                </tbody>
            </table>
        </div>`;
    }

    /**
     * Cria a linha da tabela para cada mudança seguindo o HTML original
     */
    function createChangeRowHTML(change, idx) {
        let contentHtml = '';

        if (change.tipo.endsWith('_imagem')) {
            contentHtml = escapeHtml(change.texto);
        } else if (change.tipo === 'alteracao') {
            contentHtml = `
                <dl>
                    <dt>De:</dt>
                    <dd><del>${escapeHtml(change.antes)}</del></dd>
                    <dt>Para:</dt>
                    <dd><ins>${escapeHtml(change.depois)}</ins></dd>
                </dl>`;
        } else {
            const elementClass = change.tipo === 'adicao' ? 'ins' : 'del';
            contentHtml = `<${elementClass}>${escapeHtml(change.texto)}</${elementClass}>`;
        }

        return `
            <tr data-change-idx="${idx}">
                <td>${LABEL_MAP[change.tipo]}</td>
                <td>${contentHtml}</td>
            </tr>`;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    /**
     * Inicializa o processamento
     */
    function init() {
        const dataEl = findDataElement();
        const changesList = document.getElementById('changes-list');
        if (!dataEl || !changesList) return;

        try {
            const changesData = JSON.parse(dataEl.textContent || '[]');

            if (changesData.length === 0) {
                changesList.innerHTML = '<p class="alert alert-warning">Nenhuma alteração identificada.</p>';
                return;
            }

            const rowsHtml = changesData.map((c, i) => createChangeRowHTML(c, i)).join('');
            changesList.innerHTML = createTableWrapper(rowsHtml);
        } catch (e) {
            console.error('Erro ao processar alterações:', e);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
