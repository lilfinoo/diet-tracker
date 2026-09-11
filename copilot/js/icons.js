(() => {
    const iconAttributes = {
        width: '1em',
        height: '1em',
        'stroke-width': 2,
        'aria-hidden': 'true',
        focusable: 'false'
    };
    let renderQueued = false;

    function renderIcons() {
        renderQueued = false;
        if (!window.lucide) return;
        window.lucide.createIcons({ attrs: iconAttributes, root: document });
    }

    function queueIconRender() {
        if (renderQueued) return;
        renderQueued = true;
        window.requestAnimationFrame(renderIcons);
    }

    const observer = new MutationObserver((mutations) => {
        const hasNewIcon = mutations.some(({ addedNodes }) => Array.from(addedNodes).some((node) =>
            node.nodeType === Node.ELEMENT_NODE &&
            (node.matches?.('[data-lucide]') || node.querySelector?.('[data-lucide]'))
        ));
        if (hasNewIcon) queueIconRender();
    });

    renderIcons();
    observer.observe(document.body, { childList: true, subtree: true });
})();
