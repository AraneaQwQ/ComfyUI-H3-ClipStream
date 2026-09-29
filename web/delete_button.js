// RAFOLIE: scoped card action; never acts on the Auto selector.
export function addDeleteButton(parent, { description, onDelete, signal }) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "h3-asset-delete";
    button.title = `删除 ${description}`;
    button.setAttribute("aria-label", button.title);
    button.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
    button.addEventListener("dblclick", event => event.stopPropagation());
    button.addEventListener("click", async event => {
        event.stopPropagation();
        if (button.disabled || signal.aborted) return;
        if (!window.confirm(`永久删除 ${description}？\n将删除该卡片对应的素材文件、预览和索引；此操作无法撤销。`)) return;
        button.disabled = true;
        try {
            await onDelete();
        } catch (error) {
            if (!signal.aborted) window.alert(error.message || "删除失败，请刷新后重试。");
        } finally {
            button.disabled = false;
        }
    });
    parent.appendChild(button);
    return button;
}
