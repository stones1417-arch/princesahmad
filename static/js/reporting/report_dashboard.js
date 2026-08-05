(() => {
    const page = document.querySelector('.enterprise-report-page');
    const toggle = document.querySelector('[data-report-menu]');
    const backdrop = document.querySelector('[data-report-backdrop]');
    if (!page || !toggle) return;

    const setMenu = (open) => {
        page.classList.toggle('menu-open', open);
        toggle.setAttribute('aria-expanded', String(open));
        document.body.style.overflow = open ? 'hidden' : '';
    };

    toggle.addEventListener('click', () => setMenu(!page.classList.contains('menu-open')));
    backdrop?.addEventListener('click', () => setMenu(false));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') setMenu(false);
    });
    window.addEventListener('resize', () => {
        if (window.innerWidth > 900) setMenu(false);
    });
})();
