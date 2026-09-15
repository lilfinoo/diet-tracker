(() => {
    const iconAttributes = {
        width: '1em',
        height: '1em',
        'stroke-width': 2,
        'aria-hidden': 'true',
        focusable: 'false'
    };
    let renderQueued = false;
    const roots = new Set();

    function renderIcons() {
        renderQueued = false;
        if (!window.lucide) return;
        roots.forEach(root => {
            if (root.isConnected !== false) window.lucide.createIcons({ attrs: iconAttributes, root });
        });
        roots.clear();
    }

    function queueIconRender(root) {
        if (!root) return;
        roots.add(root);
        if (renderQueued) return;
        renderQueued = true;
        window.requestAnimationFrame(renderIcons);
    }

    const observer = new MutationObserver((mutations) => {
        mutations.forEach(({ addedNodes }) => Array.from(addedNodes).forEach(node => {
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            if (node.matches?.('[data-lucide]')) queueIconRender(node.parentElement);
            else if (node.querySelector?.('[data-lucide]')) queueIconRender(node);
        }));
    });

    roots.add(document);
    renderIcons();
    observer.observe(document.body, { childList: true, subtree: true });
})();
