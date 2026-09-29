// RAFOLIE 2026-09-28: DOM widget sizing shared by Canvas and Nodes 2.0.
export function addPanel(node, name, element, minHeight = 220) {
    const lifetime = new AbortController();
    element.style.width = "100%";
    element.style.height = "100%";
    element.style.minWidth = "0";
    element.style.minHeight = "0";
    element.style.overflow = "hidden";
    for (const type of ["pointerdown", "mousedown", "click", "dblclick", "wheel"]) {
        element.addEventListener(type, event => event.stopPropagation(), { signal: lifetime.signal });
    }
    const widget = node.addDOMWidget(name, "h3-panel", element, {
        serialize: false,
        hideOnZoom: false,
        canvasOnly: false,
        getMinHeight: () => minHeight,
    });
    widget.serialize = false;
    const onRemove = widget.onRemove;
    widget.onRemove = function () {
        lifetime.abort();
        return onRemove?.apply(this, arguments);
    };
    return { widget, signal: lifetime.signal };
}
