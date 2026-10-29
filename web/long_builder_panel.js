// Long Builder panel: choose the shots by card instead of typing ids, get one film back.
//
// The node needs a project name, the list of switched-off cards and the card order, so
// this panel is a view over the same widgets the Clip Bin Picker uses:
// - a project dropdown fed by /minimax/clip_bin/projects (bins with archived video only)
// - a card deck whose order is the order of the film: the button on a card leaves a take
//   out of the film, dragging a card moves it along the timeline
// - the resolution and duration measured from the archived video, not from the latent
// - a summary line that says exactly what will be joined, and why anything is skipped
// - a node that keeps the size you gave it: zoom changes the cards, and a refresh never
//   moves the node - only the fit button and the zoom buttons change its height
// - the finished film on the node, which can be put away while the cards are arranged
import { addPanel } from "./dom_panel.js";
import { moveCard, resolveDeckOrder, shotNumber } from "./long_builder_order.js";
import {
    DECK_PAD_V,
    ZOOM_STEPS,
    cardMinFor,
    planFitHeight,
    planZoomHeight,
    stepIndex,
    thumbHeightFor,
    zoomPercent,
} from "./long_builder_fit.js";
import {
    PLAYBACK_SPEED_OPTIONS,
    normalizeCustomSpeed,
    restoredDuration,
    sourcePlaybackSpeed,
    speedDescription,
    speedOptionLabel,
} from "./long_builder_speed.js";
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function useStylesheet(file, styleId) {
    if (document.getElementById(styleId)) return;
    const link = document.createElement("link");
    link.id = styleId;
    link.rel = "stylesheet";
    link.type = "text/css";
    link.href = new URL(file, import.meta.url).href;
    document.head.appendChild(link);
}

// Card look is shared with the Clip Bin deck; the panel chrome is its own.
useStylesheet("./clip_bin_picker.css", "minimax-clip-bin-styles");
useStylesheet("./long_builder.css", "minimax-long-builder-styles");

app.registerExtension({
    name: "MiniMaxH3.ClipLongBuilder",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "MiniMaxClipBinLongBuilder") {
            return;
        }
        nodeType.prototype.min_size = [340, 240];

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            if (this.size[0] < 340 || this.size[1] < 240) {
                this.setSize([Math.max(this.size[0], 340), Math.max(this.size[1], 380)]);
            }
            setupLongBuilderPanel(this);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            this._h3LongRefresh?.();
            return r;
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted ? onExecuted.apply(this, arguments) : undefined;
            this._h3LongResult?.(message);
            this._h3LongRefresh?.();
            return r;
        };

        // ComfyUI shows the joined video as a DOM widget of its own. Catch it at the
        // moment it is created so the panel can hide it again when the user had it away -
        // a hidden widget is left out of the node layout, which is what makes the node
        // compact instead of leaving a blank strip behind.
        const addDOMWidget = nodeType.prototype.addDOMWidget;
        nodeType.prototype.addDOMWidget = function (name, type, element, options) {
            const widget = addDOMWidget ? addDOMWidget.apply(this, arguments) : undefined;
            if (type === "video" && widget) this._h3FilmShown?.();
            return widget;
        };
    }
});

// The card shows the archived video as it will be joined: measured pixels and seconds.
function videoSpec(card) {
    const width = Number(card.video_width) || 0;
    const height = Number(card.video_height) || 0;
    const seconds = Number(card.video_duration_seconds) || 0;
    const size = width && height ? `${width}×${height}` : "—";
    const duration = seconds > 0 ? `${seconds.toFixed(2)}s` : "—";
    return `${size} · ${duration}`;
}

// Cards are laid out in a grid, so the drop side is decided along the row the pointer
// is over: left half inserts before the card, right half after it.
function dropBefore(event, element) {
    const rect = element.getBoundingClientRect();
    return event.clientX < rect.left + rect.width / 2;
}
function parseExcluded(text) {
    return String(text || "").split(/[,\n;]+/).map(part => part.trim()).filter(Boolean);
}

// The panel's own floor, used both when the DOM widget is created and when the node is
// sized: below this the deck overflows the node instead of getting smaller. One number for
// both places, so the sizing maths cannot drift away from the widget.
const PANEL_MIN_HEIGHT = 680;

const JOIN_OPTION_LABELS = {
    "auto（参数一致无损直拷，否则重编码）": "auto · 视频直拷 / 音频归一",
    "copy（只允许无损直拷，参数不一致报错）": "copy · 视频直拷 / 音频归一",
    "reencode（统一重编码）": "reencode · 重编码",
};

function createSection(index, title, className) {
    const section = document.createElement("section");
    section.className = `h3-lb-section ${className}`;
    const heading = document.createElement("div");
    heading.className = "h3-lb-section-heading";
    const number = document.createElement("span");
    number.className = "h3-lb-section-index";
    number.textContent = index;
    const text = document.createElement("span");
    text.className = "h3-lb-section-title";
    text.textContent = title;
    const actions = document.createElement("div");
    actions.className = "h3-lb-section-actions";
    heading.append(number, text, actions);
    const body = document.createElement("div");
    body.className = "h3-lb-section-body";
    section.append(heading, body);
    return { section, heading, body, actions };
}

function setupLongBuilderPanel(node) {
    const projectWidget = node.widgets?.find(w => w.name === "project_name");
    const excludeWidget = node.widgets?.find(w => w.name === "exclude_clips");
    const orderWidget = node.widgets?.find(w => w.name === "clip_order");
    const variantWidget = node.widgets?.find(w => w.name === "variant_policy");
    const joinWidget = node.widgets?.find(w => w.name === "join_mode");
    const fpsWidget = node.widgets?.find(w => w.name === "fps");
    const outputNameWidget = node.widgets?.find(w => w.name === "output_name");
    const speedWidget = node.widgets?.find(w => w.name === "playback_speed");
    const speedCustomWidget = node.widgets?.find(w => w.name === "playback_speed_custom");

    for (const widget of [
        projectWidget, excludeWidget, orderWidget, variantWidget, joinWidget,
        fpsWidget, outputNameWidget, speedWidget, speedCustomWidget,
    ]) {
        if (widget?.options) widget.options.hidden = true;
    }

    const container = document.createElement("div");
    container.className = "minimax-clip-bin-container h3-lb-container";

    const library = createSection("02", "项目与卡片", "h3-lb-library");
    const projectRow = document.createElement("div");
    projectRow.className = "h3-lb-project-row";
    const projectSelect = document.createElement("select");
    projectSelect.className = "minimax-clip-bin-project";
    projectSelect.title = "选择包含视频文件的项目文件夹";
    const refreshBtn = document.createElement("button");
    refreshBtn.className = "minimax-clip-bin-refresh-btn";
    refreshBtn.textContent = "🔄 刷新";
    projectRow.append(projectSelect, refreshBtn);
    library.body.appendChild(projectRow);

    const cardToolbar = document.createElement("div");
    cardToolbar.className = "h3-lb-card-toolbar";
    const cardToolLabel = document.createElement("span");
    cardToolLabel.className = "h3-lb-tool-label";
    cardToolLabel.textContent = "卡片显示";
    const actionsWrap = document.createElement("div");
    actionsWrap.className = "minimax-clip-bin-actions";
    const zoomOutBtn = document.createElement("button");
    zoomOutBtn.className = "minimax-clip-bin-refresh-btn";
    zoomOutBtn.textContent = "−";
    zoomOutBtn.title = "缩小卡片（100%-400%，不改变节点宽度）";
    const zoomLabel = document.createElement("span");
    zoomLabel.className = "minimax-clip-bin-zoom-label";
    zoomLabel.textContent = "100%";
    const zoomInBtn = document.createElement("button");
    zoomInBtn.className = "minimax-clip-bin-refresh-btn";
    zoomInBtn.textContent = "+";
    zoomInBtn.title = "放大卡片（100%-400%，不改变节点宽度）";
    const fitBtn = document.createElement("button");
    fitBtn.className = "minimax-clip-bin-refresh-btn";
    fitBtn.textContent = "⤢ 适应";
    fitBtn.title = "按当前宽度显示两行卡片（其余滚动）";
    actionsWrap.appendChild(zoomOutBtn);
    actionsWrap.appendChild(zoomLabel);
    actionsWrap.appendChild(zoomInBtn);
    actionsWrap.appendChild(fitBtn);
    cardToolbar.append(cardToolLabel, actionsWrap);
    library.body.appendChild(cardToolbar);

    const summary = document.createElement("div");
    summary.className = "h3-lb-summary";
    library.body.appendChild(summary);

    // The deck order is the film order, so the panel says which rule it is using and
    // keeps the way back to shot-number order next to the cards it affects.
    const orderBar = document.createElement("div");
    orderBar.className = "h3-lb-order-bar";
    const orderHint = document.createElement("span");
    orderHint.className = "h3-lb-order-hint";
    const orderReset = document.createElement("button");
    orderReset.className = "h3-lb-order-reset";
    orderReset.type = "button";
    orderReset.textContent = "↺ 按镜头序号";
    orderReset.title = "清除手动顺序，恢复按镜头序号拼接";
    orderReset.hidden = true;
    orderBar.appendChild(orderHint);
    orderBar.appendChild(orderReset);
    library.body.appendChild(orderBar);

    const deck = document.createElement("div");
    deck.className = "minimax-clip-bin-deck h3-lb-deck";
    library.body.appendChild(deck);

    const settings = createSection("01", "拼接与速度", "h3-lb-settings");
    const settingsGrid = document.createElement("div");
    settingsGrid.className = "h3-lb-settings-grid";
    settings.body.appendChild(settingsGrid);
    const speedNote = document.createElement("div");
    speedNote.className = "h3-lb-speed-note";
    settings.body.appendChild(speedNote);

    const preview = createSection("03", "成片预览", "h3-lb-preview");
    const footerText = document.createElement("span");
    footerText.className = "h3-lb-footer-text";
    footerText.textContent = "运行后在这里显示成片位置，节点上可直接预览。";
    const filmToggle = document.createElement("button");
    filmToggle.className = "h3-lb-film-toggle";
    filmToggle.type = "button";
    filmToggle.disabled = true;
    filmToggle.textContent = "▶ 展开成片";
    preview.actions.appendChild(filmToggle);
    preview.body.appendChild(footerText);

    container.append(settings.section, library.section, preview.section);

    const { signal } = addPanel(node, "h3_long_builder", container, PANEL_MIN_HEIGHT);
    const settingRecords = [];

    function updateWidget(widget, value) {
        widget.value = value;
        widget.callback?.(value);
        node.setDirtyCanvas?.(true, true);
        refreshSettings();
    }

    function addSetting(widget, labelText, kind, config = {}) {
        if (!widget) return;
        const field = document.createElement("label");
        field.className = "h3-lb-field";
        field.dataset.field = widget.name;
        const label = document.createElement("span");
        label.className = "h3-lb-field-label";
        const labelTextElement = document.createElement("span");
        labelTextElement.textContent = labelText;
        const note = document.createElement("span");
        note.className = "h3-lb-field-note";
        label.append(labelTextElement, note);
        let control;
        if (kind === "combo") {
            control = document.createElement("select");
            const configured = typeof widget.options?.values === "function"
                ? widget.options.values() : widget.options?.values;
            const values = config.values || (Array.isArray(configured) ? configured : []);
            for (const value of values) {
                const option = document.createElement("option");
                option.value = String(value);
                option.textContent = config.labels?.[value]
                    ?? widget.options?.getOptionLabel?.(value) ?? String(value);
                control.appendChild(option);
            }
        } else {
            control = document.createElement("input");
            control.type = kind === "number" ? "number" : "text";
            if (kind === "number") {
                control.min = String(config.min ?? widget.options?.min ?? "");
                control.max = String(config.max ?? widget.options?.max ?? "");
                control.step = String(config.step ?? widget.options?.step ?? "any");
            } else {
                control.placeholder = config.placeholder || "";
            }
        }
        control.className = "h3-lb-field-control";
        control.addEventListener("change", () => {
            let value = control.value;
            if (kind === "number") {
                if (config.normalize) {
                    value = config.normalize(control.value, widget.value);
                } else {
                    value = Number(control.value);
                    if (!Number.isFinite(value)) value = Number(widget.value) || config.fallback || 0;
                    const step = Number(config.step) || 0;
                    if (step > 0) value = Math.round(value / step) * step;
                    if (Number.isFinite(Number(config.min))) value = Math.max(Number(config.min), value);
                    if (Number.isFinite(Number(config.max))) value = Math.min(Number(config.max), value);
                    value = Number(value.toFixed(6));
                }
            }
            updateWidget(widget, value);
        }, { signal });
        control.addEventListener("keydown", event => {
            if (event.key === "Enter") control.blur();
        }, { signal });
        field.append(label, control);
        settingsGrid.appendChild(field);
        settingRecords.push({ field, widget, control, note, config });
    }

    function refreshSettings() {
        for (const record of settingRecords) {
            const { field, widget, control, note, config } = record;
            const enabled = config.enabled ? Boolean(config.enabled()) : true;
            control.disabled = !enabled;
            field.classList.toggle("is-disabled", !enabled);
            note.textContent = config.note?.() || "";
            if (document.activeElement !== control) control.value = String(widget.value ?? "");
        }
        const sourceSpeed = sourcePlaybackSpeed(speedWidget?.value, speedCustomWidget?.value);
        const copyConflict = sourceSpeed < 1 && String(joinWidget?.value || "").startsWith("copy");
        speedNote.textContent = speedDescription(speedWidget?.value, speedCustomWidget?.value, fpsWidget?.value)
            + (copyConflict ? " 当前 copy 不可恢复，请改用 auto / reencode。" : "");
        speedNote.classList.toggle("is-warning", copyConflict);
    }

    addSetting(variantWidget, "视频变体", "combo");
    addSetting(joinWidget, "拼接方式", "combo", { labels: JOIN_OPTION_LABELS });
    addSetting(fpsWidget, "基准帧率", "number", {
        min: 1, max: 240, step: 0.001,
        enabled: () => !String(joinWidget?.value || "").startsWith("copy"),
        note: () => String(joinWidget?.value || "").startsWith("copy") ? "copy 不用" : "",
    });
    addSetting(outputNameWidget, "输出文件名", "text", { placeholder: "留空自动命名" });
    addSetting(speedWidget, "切片慢放倍率", "combo", {
        values: PLAYBACK_SPEED_OPTIONS,
        labels: Object.fromEntries(PLAYBACK_SPEED_OPTIONS.map(value => [value, speedOptionLabel(value)])),
    });
    addSetting(speedCustomWidget, "自定义慢放倍率", "number", {
        min: 0.1, max: 1, step: 0.1,
        normalize: normalizeCustomSpeed,
        enabled: () => speedWidget?.value === "custom",
        note: () => speedWidget?.value === "custom" ? "" : "仅 custom",
    });
    refreshSettings();
    const previewCleanups = new Set();
    const releasePreviews = () => {
        for (const cleanup of previewCleanups) cleanup();
        previewCleanups.clear();
    };
    signal.addEventListener("abort", releasePreviews, { once: true });

    // --- Card size, and the area that shows it ------------------------------------
    // The same zoom steps and the same card base as the Clip Bin picker, so a card is
    // the same size in both panels. The choice is remembered in this browser: nobody
    // wants to set it again after a page reload.
    const ZOOM_STORE_KEY = "h3.clipstream.longBuilder.cardZoom";
    let cardCount = 0;
    let autoFit = true; // one fit for a node that has never been sized, then never again
    let zoomIdx = readStoredZoom();

    function readStoredZoom() {
        try {
            return stepIndex(window.localStorage.getItem(ZOOM_STORE_KEY), 0);
        } catch (e) {
            return 0;
        }
    }

    function storeZoom() {
        try {
            window.localStorage.setItem(ZOOM_STORE_KEY, String(zoomIdx));
        } catch (e) {
            // Private mode: the zoom simply is not remembered.
        }
    }

    function applyCardZoom() {
        container.style.setProperty("--card-min", cardMinFor(zoomIdx) + "px");
        container.style.setProperty("--thumb-h", thumbHeightFor(zoomIdx) + "px");
        zoomLabel.textContent = zoomPercent(zoomIdx) + "%";
        zoomOutBtn.disabled = zoomIdx <= 0;
        zoomInBtn.disabled = zoomIdx >= ZOOM_STEPS.length - 1;
        storeZoom();
    }

    // The deck is the only part of the panel that grows, so measure what the panel keeps
    // for itself and ask for the deck the current zoom needs. The width is never part of
    // this: it is the size the user gave the node, and a deck that does not fit scrolls.
    function deckGeometry() {
        const sample = deck.querySelector(".h3-lb-card");
        return {
            deckWidth: deck.clientWidth,
            deckHeight: deck.offsetHeight,
            chromeHeight: Math.max(0, container.offsetHeight - deck.offsetHeight),
            rowHeight: sample?.offsetHeight || 0,
        };
    }

    // The node has a floor of its own: the panel widget is never shorter than
    // PANEL_MIN_HEIGHT, so sizing the node below that does not shrink the deck - the deck
    // overflows the node, the next measurement still sees a tall deck, and the node drifts
    // smaller on every reload. The floor is part of the maths instead.
    function nodeChromeHeight() {
        return Math.max(0, (node.size?.[1] || 0) - (container.offsetHeight || 0));
    }

    function heightFloor() {
        const minSize = node.min_size?.[1] || 240;
        // Before the panel has been laid out there is nothing to measure; asking for
        // "node height + PANEL_MIN_HEIGHT" then would grow the node for no reason.
        if (!(container.offsetHeight > 0)) return minSize;
        return Math.max(minSize, nodeChromeHeight() + PANEL_MIN_HEIGHT);
    }

    function applyHeight(height) {
        const wanted = Math.max(heightFloor(), Math.round(Number(height)) || 0);
        if (Math.abs(wanted - node.size[1]) > 2) {
            node.setSize([node.size[0], wanted]);
        }
    }

    // The fit button: the width stays as it is, the deck becomes tall enough for the rows
    // this width produces at the current card size.
    function fitPanel() {
        const before = deckGeometry();
        const wanted = planFitHeight({
            count: cardCount,
            deckWidth: before.deckWidth,
            zoomIdx,
            rowHeight: before.rowHeight,
            chromeHeight: before.chromeHeight,
            padV: DECK_PAD_V,
            viewHeight: Math.floor(window.innerHeight * 0.9),
        });
        if (wanted <= 0) return;
        sizeDeckTo(wanted);
    }

    // + and -: the same rows, bigger or smaller cards. The row count is read before the
    // CSS changes and the new card height after, so the deck grows by exactly the
    // difference in row height - which is what zooming should feel like.
    function zoomFit(before) {
        if (!before.rowHeight) return;
        const after = deckGeometry();
        if (!after.rowHeight) return;
        const wanted = planZoomHeight({
            deckHeight: before.deckHeight,
            rowHeightBefore: before.rowHeight,
            rowHeightAfter: after.rowHeight,
            chromeHeight: after.chromeHeight,
            padV: DECK_PAD_V,
            viewHeight: Math.floor(window.innerHeight * 0.9),
        });
        if (wanted <= 0) return;
        sizeDeckTo(wanted);
    }

    // Ask for a deck this tall, then look at what the layout actually gave us. litegraph
    // splits the node's free space between every growable widget, so with the film preview
    // on the node the deck only gets half of what is asked for and each pass closes half of
    // what is left - a few passes, and it stops as soon as it is within 8px. A deck that did
    // not move at all means the node is sitting on its floor: stop instead of pushing.
    function sizeDeckTo(wantedDeck, rounds = 4) {
        const before = deckGeometry();
        applyHeight(node.size[1] + (wantedDeck - before.deckHeight));
        if (rounds <= 0) return;
        requestAnimationFrame(() => {
            if (signal.aborted) return;
            const now = deckGeometry();
            if (Math.abs(wantedDeck - now.deckHeight) <= 8) return;
            if (Math.abs(now.deckHeight - before.deckHeight) <= 2) return;
            sizeDeckTo(wantedDeck, rounds - 1);
        });
    }

    // The cards have to be laid out before their height means anything.
    function scheduleFit(work) {
        const run = work || fitPanel;
        requestAnimationFrame(() => {
            if (!signal.aborted) run();
        });
    }

    // A node that has never been sized gets one fit, so it does not open as a small box
    // with two cards in it. After that the panel never touches the height on its own:
    // pressing refresh must not move a node the user just placed.
    function fitOnce() {
        if (!autoFit) return;
        autoFit = false;
        scheduleFit();
    }

    // --- The finished film, and putting it away ----------------------------------
    // The film is the tallest thing on the node, and it is in the way while the cards are
    // being arranged. So the panel can put ComfyUI's preview away and give the room back.
    // The choice is remembered in this browser, like the card size.
    const FILM_STORE_KEY = "h3.clipstream.longBuilder.filmPreview";
    let filmHidden = readStoredFilmHidden();
    let filmHeight = 0; // what the preview took, so collapsing gives the same room back
    let heightWithFilm = 0; // the node height the preview fitted into, for expanding back

    function readStoredFilmHidden() {
        try {
            return window.localStorage.getItem(FILM_STORE_KEY) === "hidden";
        } catch (e) {
            return false;
        }
    }

    function storeFilmHidden() {
        try {
            window.localStorage.setItem(FILM_STORE_KEY, filmHidden ? "hidden" : "shown");
        } catch (e) {
            // Private mode: the choice simply is not remembered.
        }
    }

    // The preview widget is ComfyUI's own, and only exists once there is an output.
    function filmWidget() {
        return (node.widgets || []).find(widget => widget.type === "video") || null;
    }

    function filmHeightOf(widget) {
        const height = widget?.computedHeight || widget?.element?.offsetHeight || 0;
        return Math.max(0, Math.round(Number(height)) || 0);
    }

    function updateFilmToggle() {
        const has = Boolean(filmWidget());
        filmToggle.disabled = !has;
        filmToggle.textContent = filmHidden ? "▶ 展开成片" : "▼ 收起成片";
        filmToggle.title = !has
            ? "运行后这里可以收起/展开成片预览"
            : (filmHidden ? "展开拼接好的视频预览" : "收起视频预览，节点可以更小");
    }

    function setFilmShown(shown, options) {
        const resize = (options || {}).resize !== false;
        const widget = filmWidget();
        filmHidden = !shown;
        storeFilmHidden();
        if (widget) {
            widget.hidden = !shown;
            if (widget.element) widget.element.style.display = shown ? "" : "none";
        }
        updateFilmToggle();
        node.setDirtyCanvas?.(true, true);
        // Remember where the preview fitted, even when this call must not resize anything
        // (a page reload re-applies the saved choice): expanding goes back to this height.
        if (!shown) heightWithFilm = node.size[1];
        if (!widget || !resize) return;
        if (shown) {
            // Go back to the exact height the preview fitted into. Never add: litegraph
            // splits the node's free space between every growable widget (distributeSpace,
            // called from LGraphNode._arrangeWidgets), so the preview takes its share of the
            // room by itself - adding its height on top is what made the node longer on
            // every expand, and the share grows with the node, so it never settled.
            // Never shrink on expand either: if the node was made bigger while the preview
            // was away, that choice stays - restoring is a floor, not an override.
            if (heightWithFilm) applyHeight(Math.max(heightWithFilm, node.size[1]));
        } else {
            filmHeight = filmHeightOf(widget) || filmHeight;
            if (filmHeight) applyHeight(node.size[1] - filmHeight);
        }
    }

    // Called when ComfyUI adds the preview widget: re-apply the user's choice to the new
    // widget, without touching the node size.
    node._h3FilmShown = () => setFilmShown(!filmHidden, { resize: false });
    if (filmHidden) node._h3FilmShown();

    filmToggle.onclick = (e) => {
        e.stopPropagation();
        setFilmShown(filmHidden);
    };

    const currentProject = () => (projectWidget?.value || "Default_Project");
    const excluded = () => new Set(parseExcluded(excludeWidget?.value));
    const orderText = () => String(orderWidget?.value || "");

    function setExcluded(clipId, off) {
        const list = parseExcluded(excludeWidget?.value);
        const at = list.indexOf(clipId);
        if (off && at < 0) list.push(clipId);
        if (!off && at >= 0) list.splice(at, 1);
        if (!excludeWidget) return;
        excludeWidget.value = list.join(",");
        excludeWidget.callback?.(excludeWidget.value);
        node.setDirtyCanvas?.(true, true);
    }

    // One click puts every switched-off card back. The order widget is left alone, so a
    // hand-dragged film keeps its shape and only the exclusions disappear.
    function restoreAll() {
        if (!excludeWidget) return;
        excludeWidget.value = "";
        excludeWidget.callback?.("");
        node.setDirtyCanvas?.(true, true);
        loadCards();
    }

    // The whole point of the drag: the card order becomes the node input.
    function setOrder(ids) {
        if (!orderWidget) return;
        orderWidget.value = ids.join(",");
        orderWidget.callback?.(orderWidget.value);
        node.setDirtyCanvas?.(true, true);
    }

    async function loadProjects() {
        let names = [];
        try {
            const res = await api.fetchApi("/minimax/clip_bin/projects?videos_only=1", { cache: "no-store" });
            if (res.ok) {
                const data = await res.json();
                names = (data.projects || []).map(item => ({
                    name: item.name, clips: item.clips || 0, videos: item.videos || 0,
                }));
            }
        } catch (e) {
            console.warn("[Long Builder] projects lookup failed:", e);
        }
        if (signal.aborted) return;
        const active = currentProject();
        if (!names.some(item => item.name === active)) {
            names.unshift({ name: active, clips: 0, videos: 0 });
        }
        projectSelect.innerHTML = "";
        for (const item of names) {
            const option = document.createElement("option");
            option.value = item.name;
            option.textContent = item.videos ? `${item.name} (${item.videos} 段视频)` : item.name;
            if (item.name === active) option.selected = true;
            projectSelect.appendChild(option);
        }
    }

    let lastDescription = null;

    function describe(joined, cards, offSet) {
        lastDescription = { joined, cards, offSet };
        const names = joined.map(card => card.shot_tag || card.clip_id);
        const shown = names.length <= 8 ? names.join(" → ") : names.slice(0, 8).join(" → ") + " …";
        const lines = [];
        // The durations are measured, so the total is the real length of the film.
        const timed = joined.length > 0
            && joined.every(card => Number(card.video_duration_seconds) > 0);
        const total = joined.reduce((sum, card) => sum + Number(card.video_duration_seconds || 0), 0);
        const sourceSpeed = sourcePlaybackSpeed(speedWidget?.value, speedCustomWidget?.value);
        const restoredTotal = restoredDuration(total, speedWidget?.value, speedCustomWidget?.value);
        const durationText = timed
            ? sourceSpeed < 1
                ? ` · 慢放 ${total.toFixed(1)} 秒 → 成片 ${restoredTotal.toFixed(1)} 秒`
                : ` · 约 ${total.toFixed(1)} 秒`
            : "";
        lines.push(joined.length
            ? `将拼接 ${joined.length} 段${durationText}：${shown}`
            : "没有可拼接的片段：卡片全被排除，或都没有归档视频");
        const usable = cards.filter(card => card.has_video);
        const offCount = usable.length - joined.length;
        const noVideo = cards.filter(card => !card.has_video);
        if (noVideo.length) {
            lines.push(`⚠ ${noVideo.length} 段没有归档视频，会自动跳过：${noVideo.map(card => card.shot_tag || card.clip_id).slice(0, 6).join("、")}`);
        }
        const numbers = usable.map(card => shotNumber(card.shot_tag)).filter(n => n !== null);
        if (numbers.length > 1) {
            const present = new Set(numbers);
            const holes = [];
            for (let n = Math.min(...numbers); n <= Math.max(...numbers); n++) {
                if (!present.has(n)) holes.push("Shot " + n);
            }
            if (holes.length) lines.push("⚠ 库里没有 " + holes.join("、") + " 这段卡片");
        }
        summary.innerHTML = lines.map(line => `<div>${line}</div>`).join("");
        // Saying "you can add them back" is not a way to do it: the row carries the button.
        if (offCount) {
            const row = document.createElement("div");
            row.className = "h3-lb-restore-row";
            const note = document.createElement("span");
            note.textContent = `已排除 ${offCount} 段，排在卡片墙最后`;
            row.appendChild(note);
            const restore = document.createElement("button");
            restore.type = "button";
            restore.className = "h3-lb-restore-all";
            restore.textContent = "↺ 全部加回";
            restore.title = "清空排除列表，所有有归档视频的卡片重新进入成片";
            restore.onclick = (e) => {
                e.stopPropagation();
                restoreAll();
            };
            row.appendChild(restore);
            summary.appendChild(row);
        }
    }

    function showOrderMode(isManual) {
        orderHint.textContent = isManual
            ? "顺序：手动（拖动卡片可继续调整）"
            : "顺序：按镜头序号（把卡片拖到别处即可手动排序）";
        orderHint.classList.toggle("h3-lb-order-manual", isManual);
        orderReset.hidden = !isManual;
    }
    let requestId = 0;
    async function loadCards() {
        refreshSettings();
        const currentRequest = ++requestId;
        await loadProjects();
        if (signal.aborted || currentRequest !== requestId) return;
        const project = currentProject();
        // Ask for the variant this node would join, so the numbers on a card are the
        // numbers that end up in the film. probe=1 is what makes the backend measure
        // the file; the Pickers send neither parameter and pay no ffprobe cost.
        const policy = encodeURIComponent(variantWidget?.value || "");
        const listUrl = "/minimax/clip_bin/list?project=" + encodeURIComponent(project)
            + "&variant_policy=" + policy + "&probe=1";
        try {
            const res = await api.fetchApi(listUrl, { cache: "no-store" });
            if (signal.aborted || currentRequest !== requestId) return;
            releasePreviews();
            deck.innerHTML = "";
            if (!res.ok) {
                summary.innerHTML = "<div>未连接到后台服务，请刷新 ComfyUI 页面后重试。</div>";
                return;
            }
            const data = await res.json();
            const cards = data.clips || [];
            cardCount = cards.length;
            const offSet = excluded();
            const ordered = resolveDeckOrder(cards, orderText(), offSet);
            const joinIds = ordered.joinIds;
            // deck is already in film order: the joining cards first, the rest after.
            const joinedCards = ordered.deck.filter(c => joinIds.includes(String(c.clip_id)));
            describe(joinedCards, cards, offSet);
            showOrderMode(orderText().trim() !== "");

            if (!cards.length) {
                const empty = document.createElement("div");
                empty.className = "h3-lb-empty";
                empty.textContent = "这个项目还没有卡片。先用 Saver 生成并归档几段视频。";
                deck.appendChild(empty);
                return;
            }

            // One drag at a time. The card itself is not clickable any more, so a drop can
            // never double as a switch; only the button on the card changes the film.
            let dragId = null;
            const clearMarkers = () => {
                for (const el of deck.querySelectorAll(".h3-lb-drop-before, .h3-lb-drop-after")) {
                    el.classList.remove("h3-lb-drop-before", "h3-lb-drop-after");
                }
            };
            const commitOrder = next => {
                clearMarkers();
                setOrder(next);
                loadCards();
            };
            deck.addEventListener("dragover", event => {
                if (dragId) event.preventDefault();
            });
            deck.addEventListener("drop", event => {
                // Empty space past the last card: move it to the end of the film.
                if (!dragId) return;
                event.preventDefault();
                commitOrder(joinIds.filter(id => id !== dragId).concat([dragId]));
            });
            ordered.deck.forEach(card => {
                const off = offSet.has(card.clip_id);
                const joinable = Boolean(card.has_video) && !off;
                const item = document.createElement("div");
                item.className = "minimax-clip-card h3-lb-card";
                if (off) item.classList.add("h3-lb-off");
                if (!card.has_video) item.classList.add("h3-lb-no-video");

                const thumbWrap = document.createElement("div");
                thumbWrap.className = "minimax-clip-thumb-wrap";
                const placeholder = '<div class="minimax-clip-thumb-placeholder">🎬</div>';
                if (card.thumbnail_url) {
                    const img = document.createElement("img");
                    img.className = "minimax-clip-thumb";
                    img.src = card.thumbnail_url;
                    img.loading = "lazy";
                    img.onerror = () => { thumbWrap.innerHTML = placeholder; };
                    thumbWrap.appendChild(img);
                } else {
                    thumbWrap.innerHTML = placeholder;
                }

                if (!card.has_video) {
                    const badge = document.createElement("div");
                    badge.className = "minimax-clip-video-badge h3-lb-badge-off";
                    badge.textContent = "无归档视频";
                    thumbWrap.appendChild(badge);
                } else if (off) {
                    const badge = document.createElement("div");
                    badge.className = "minimax-clip-active-badge h3-lb-badge-off";
                    badge.textContent = "已排除";
                    thumbWrap.appendChild(badge);
                } else {
                    // Where this segment sits in the film, so a dragged deck can be read.
                    const place = document.createElement("div");
                    const position = joinIds.indexOf(String(card.clip_id));
                    place.className = "minimax-clip-active-badge h3-lb-place";
                    place.textContent = "#" + (position + 1);
                    place.title = "成片里的位置";
                    thumbWrap.appendChild(place);
                }

                if (card.has_video && card.video_url) {
                    let hoverVideo = null;
                    let hoverTimer = null;
                    const stopHover = () => {
                        clearTimeout(hoverTimer);
                        hoverTimer = null;
                        if (hoverVideo) {
                            hoverVideo.pause();
                            hoverVideo.removeAttribute("src");
                            hoverVideo.load();
                            hoverVideo.remove();
                            hoverVideo = null;
                        }
                    };
                    previewCleanups.add(stopHover);
                    item.addEventListener("mouseenter", () => {
                        if (signal.aborted) return;
                        stopHover();
                        hoverTimer = setTimeout(() => {
                            if (signal.aborted || !item.isConnected || hoverVideo) return;
                            hoverVideo = document.createElement("video");
                            hoverVideo.className = "minimax-clip-hover-video";
                            hoverVideo.src = card.video_url;
                            hoverVideo.muted = true;
                            hoverVideo.loop = true;
                            hoverVideo.playsInline = true;
                            thumbWrap.appendChild(hoverVideo);
                            hoverVideo.play().catch(() => {});
                            hoverVideo.style.opacity = "1";
                        }, 220);
                    });
                    item.addEventListener("mouseleave", stopHover);
                }
                item.appendChild(thumbWrap);

                const body = document.createElement("div");
                body.className = "minimax-clip-body";
                const shotName = document.createElement("div");
                shotName.className = "minimax-clip-shot-name";
                shotName.textContent = card.shot_tag || "Shot";
                shotName.title = (card.shot_tag || "") + " (" + card.clip_id + ")";
                body.appendChild(shotName);
                const metrics = document.createElement("div");
                metrics.className = "minimax-clip-metrics";
                metrics.textContent = videoSpec(card);
                metrics.title = card.has_video
                    ? (card.video_file || "") + " · " + (card.video_frames || "?") + " 帧 · "
                        + (card.video_fps || "?") + " fps（已按归档视频实测）"
                    : "没有归档视频，读不到分辨率和时长";
                body.appendChild(metrics);
                // The switch is a labelled button on the card, not a click anywhere on it.
                // Aiming at the metrics line used to take a segment out of the film, and a
                // drag could land as a click; a button also gives the hit area real size,
                // which matters on a 9:16 card.
                if (card.has_video) {
                    const toggle = document.createElement("button");
                    toggle.type = "button";
                    toggle.className = "h3-lb-join-toggle" + (off ? " h3-lb-join-off" : "");
                    toggle.textContent = off ? "↺ 加入成片" : "⊘ 移出成片";
                    toggle.title = off
                        ? "重新参与拼接：手动排过序会回到原来的位置，否则排在成片末尾"
                        : "这一段不进成片：卡片会移到卡片墙最后，随时可以加回来";
                    toggle.onclick = (e) => {
                        e.stopPropagation();
                        setExcluded(card.clip_id, !off);
                        loadCards();
                    };
                    body.appendChild(toggle);
                }
                item.appendChild(body);
                if (joinable) {
                    item.draggable = true;
                    item.addEventListener("dragstart", event => {
                        dragId = String(card.clip_id);
                        item.classList.add("h3-lb-dragging");
                        if (event.dataTransfer) {
                            event.dataTransfer.effectAllowed = "move";
                            try {
                                event.dataTransfer.setData("text/plain", dragId);
                            } catch (e) {
                                // Some browsers refuse to build the drag payload here.
                            }
                        }
                    });
                    item.addEventListener("dragend", () => {
                        dragId = null;
                        item.classList.remove("h3-lb-dragging");
                        clearMarkers();
                    });
                    item.addEventListener("dragover", event => {
                        if (!dragId || dragId === String(card.clip_id)) return;
                        event.preventDefault();
                        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
                        clearMarkers();
                        const before = dropBefore(event, item);
                        item.classList.add(before ? "h3-lb-drop-before" : "h3-lb-drop-after");
                    });
                    item.addEventListener("drop", event => {
                        if (!dragId || dragId === String(card.clip_id)) return;
                        event.preventDefault();
                        event.stopPropagation();
                        const next = moveCard(joinIds, dragId, String(card.clip_id),
                            dropBefore(event, item));
                        commitOrder(next);
                    });
                }

                deck.appendChild(item);
            });
            fitOnce();
        } catch (e) {
            console.warn("[Long Builder] Error loading clips:", e);
        }
    }

    projectSelect.onchange = () => {
        if (projectWidget) {
            projectWidget.value = projectSelect.value;
            projectWidget.callback?.(projectWidget.value);
        }
        node.setDirtyCanvas?.(true, true);
        loadCards();
    };
    refreshBtn.onclick = (e) => {
        e.stopPropagation();
        loadCards();
    };
    zoomInBtn.onclick = (e) => {
        e.stopPropagation();
        if (zoomIdx >= ZOOM_STEPS.length - 1) return;
        const before = deckGeometry();
        zoomIdx = stepIndex(zoomIdx, 1);
        applyCardZoom();
        scheduleFit(() => zoomFit(before));
    };
    zoomOutBtn.onclick = (e) => {
        e.stopPropagation();
        if (zoomIdx <= 0) return;
        const before = deckGeometry();
        zoomIdx = stepIndex(zoomIdx, -1);
        applyCardZoom();
        scheduleFit(() => zoomFit(before));
    };
    fitBtn.onclick = (e) => {
        e.stopPropagation();
        scheduleFit();
    };
    orderReset.onclick = (e) => {
        e.stopPropagation();
        if (orderWidget) {
            orderWidget.value = "";
            orderWidget.callback?.("");
            node.setDirtyCanvas?.(true, true);
        }
        loadCards();
    };

    for (const widget of [projectWidget, variantWidget]) {
        if (!widget) continue;
        const original = widget.callback;
        // The variant policy decides which file a card reports, so the numbers on the
        // cards have to be re-read when it changes.
        widget.callback = function (v) {
            const r = original ? original.apply(this, arguments) : undefined;
            loadCards();
            return r;
        };
    }

    for (const widget of [joinWidget, fpsWidget, outputNameWidget]) {
        if (!widget) continue;
        const original = widget.callback;
        widget.callback = function (v) {
            const r = original ? original.apply(this, arguments) : undefined;
            refreshSettings();
            return r;
        };
    }

    for (const widget of [speedWidget, speedCustomWidget]) {
        if (!widget) continue;
        const original = widget.callback;
        widget.callback = function (v) {
            const r = original ? original.apply(this, arguments) : undefined;
            refreshSettings();
            if (lastDescription) {
                describe(lastDescription.joined, lastDescription.cards, lastDescription.offSet);
            }
            return r;
        };
    }

    const onChanged = event => {
        if (event.detail?.project === currentProject()) loadCards();
    };
    api.addEventListener("minimax/clip_bin/changed", onChanged);

    node._h3LongRefresh = loadCards;
    node._h3LongResult = message => {
        const first = message?.output?.images?.[0];
        if (!first) return;
        const where = first.subfolder ? `${first.subfolder}/${first.filename}` : first.filename;
        footerText.textContent = `上次输出：${where}`;
        // The preview widget appears a moment after the run finishes; the switch follows it.
        requestAnimationFrame(() => {
            if (!signal.aborted) updateFilmToggle();
        });
    };
    signal.addEventListener("abort", () => {
        api.removeEventListener("minimax/clip_bin/changed", onChanged);
        delete node._h3LongRefresh;
        delete node._h3LongResult;
        delete node._h3FilmShown;
    }, { once: true });
    applyCardZoom();
    updateFilmToggle();
    loadCards();
}
