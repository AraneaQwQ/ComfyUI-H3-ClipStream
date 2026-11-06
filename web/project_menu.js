// RAFOLIE 2026-11-03: the project bin card menu, shared by the Clip Bin Picker and
// the Long Builder panel.
//
// The menu writes through the node widget (project_name), so the graph and any saved
// workflow keep the same field; nothing here is stored twice. Selecting a card still
// only writes project_name, exactly like the dropdown it replaces.
//
// A name alone is hard to scan once a story has several bins, so each project shows
// its newest card as a cover, what it holds, and when it last changed. Create, rename
// and delete live in the same popup, and the project counts come from the same index
// the panels already read.

import { api } from "../../scripts/api.js";

const DEFAULT_PROJECT = "Default_Project";

// The Picker offers every bin - an empty one is still a valid place to save the next
// shot. The Long Builder only lists bins that already hold an archived video, because
// the rest can never become a film. Both menus act on the same folder on disk.
const MODE_CONFIG = {
    picker: {
        label: "🎞️ 项目素材库",
        labelTitle: "打开菜单可以切换项目，也可以新建、重命名或删除项目",
        placeholder: "新项目名（例如：科幻短片 01）",
        empty: "空库",
        count: (total) => `${total} 张卡片`,
        coverIcon: "🎬",
        listUrl: "/minimax/clip_bin/projects",
    },
    builder: {
        label: "🎬 项目视频库",
        labelTitle: "这里只列出含归档视频的项目；切换、新建、重命名或删除都在这个菜单里",
        placeholder: "新项目名（例如：科幻短片 01）",
        empty: "无归档视频",
        count: (total) => `${total} 段视频`,
        coverIcon: "📹",
        listUrl: "/minimax/clip_bin/projects?videos_only=1",
    },
};

// One popup at a time. Opening a second menu closes the first one, which is what a
// click outside already looks like.
let openMenuClose = null;
const projectRequests = new Map();

function fetchProjectBins(url) {
    if (!projectRequests.has(url)) {
        const request = (async () => {
            const res = await api.fetchApi(url, { cache: "no-store" });
            if (!res.ok) return [];
            const data = await res.json().catch(() => ({}));
            return Array.isArray(data.projects) ? data.projects : [];
        })().finally(() => { projectRequests.delete(url); });
        projectRequests.set(url, request);
    }
    return projectRequests.get(url);
}

function fullTime(value) {
    return String(value ?? "").trim().replace("T", " ");
}

function makeElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

export function createProjectMenu({ node, widget, signal, mode = "picker" }) {
    const config = MODE_CONFIG[mode] ?? MODE_CONFIG.picker;
    let bins = [];
    let currentPaintKey = "";
    let inFlight = null;
    let search = "";
    let editingName = "";
    let pendingDelete = "";
    let modalOpen = false;
    let sortField = "name"; // name | updated
    let sortDir = "asc";    // asc | desc
    let projectColumns = 5; // 3..6 cards per row
    const sortStoreKey = `minimax.clipBin.projectSort.${mode}`;
    const columnsStoreKey = "minimax.clipBin.projectColumns";
    try {
        const saved = JSON.parse(localStorage.getItem(sortStoreKey) || "{}");
        if (saved.field === "name" || saved.field === "updated") sortField = saved.field;
        if (saved.dir === "asc" || saved.dir === "desc") sortDir = saved.dir;
        const savedColumns = parseInt(localStorage.getItem(columnsStoreKey) || "", 10);
        if (savedColumns >= 3 && savedColumns <= 6) projectColumns = savedColumns;
    } catch (_) {
        // Private mode or a broken preference must not break the menu.
    }

    const root = document.createElement("div");

    // Row 1 - the current bin is a card, not a bare line of text. Its cover is the
    // newest card's thumbnail; clicking anywhere on it opens the grid.
    const projectRow = makeElement("div", "minimax-project-row");

    const projectLabel = makeElement("span", "minimax-project-label", config.label);
    projectLabel.title = config.labelTitle;

    const currentCard = makeElement("button", "minimax-project-current");
    currentCard.type = "button";
    currentCard.title = config.labelTitle;
    const currentCover = makeElement("div", "minimax-project-current-cover");
    const currentBody = makeElement("div", "minimax-project-current-body");
    const currentNameText = makeElement("span", "minimax-project-current-name");
    const currentMeta = makeElement("span", "minimax-project-current-meta");
    const projectCount = makeElement("span", "minimax-project-count");
    const currentUpdated = makeElement("span", "minimax-project-updated");
    currentMeta.append(projectCount, currentUpdated);
    currentBody.append(currentNameText, currentMeta);
    currentCard.append(currentCover, currentBody);

    const chevron = makeElement("span", "minimax-project-chevron", "▾");
    currentCard.append(chevron);

    const openDirBtn = makeElement("button", "minimax-project-open", "📂 打开本地目录");
    openDirBtn.type = "button";
    openDirBtn.title = "在资源管理器中打开当前项目的素材库文件夹";

    projectRow.append(projectLabel, currentCard, openDirBtn);
    root.appendChild(projectRow);

    // Popup: a fixed overlay escapes the DOM widget's overflow clipping, so the grid
    // can be larger than the node without resizing the canvas node.
    const overlay = makeElement("div", "minimax-project-overlay");
    overlay.hidden = true;
    const modal = makeElement("div", "minimax-project-modal");

    const head = makeElement("div", "minimax-project-modal-head");
    const title = makeElement("span", "minimax-project-modal-title", config.label);
    const modalCount = makeElement("span", "minimax-project-modal-count");
    const closeBtn = makeElement("button", "minimax-project-close", "✕");
    closeBtn.type = "button";
    closeBtn.title = "关闭项目菜单";
    head.append(title, modalCount, closeBtn);

    const searchRow = makeElement("div", "minimax-project-search-row");
    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.className = "minimax-project-search";
    searchInput.placeholder = "搜索项目…";
    const sortSelect = document.createElement("select");
    sortSelect.className = "minimax-project-sort";
    sortSelect.title = "项目排序字段";
    for (const [value, text] of [["name", "按名称"], ["updated", "按修改时间"]]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = text;
        sortSelect.appendChild(option);
    }
    const sortDirBtn = makeElement("button", "minimax-project-sort-dir");
    sortDirBtn.type = "button";
    const columnsSelect = document.createElement("select");
    columnsSelect.className = "minimax-project-columns";
    columnsSelect.title = "每行显示几个项目";
    for (const count of [3, 4, 5, 6]) {
        const option = document.createElement("option");
        option.value = String(count);
        option.textContent = `${count} 列`;
        columnsSelect.appendChild(option);
    }
    const newBtn = makeElement("button", "minimax-project-new-btn", "＋ 新建项目");
    newBtn.type = "button";
    newBtn.title = "把光标放进项目名称框";

    const createGroup = makeElement("div", "minimax-project-create");
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "minimax-project-name";
    nameInput.placeholder = config.placeholder;
    const createBtn = makeElement("button", "minimax-project-create-btn", "✔ 建立");
    createBtn.type = "button";
    const cancelCreateBtn = makeElement("button", "minimax-project-cancel-btn", "✕ 取消");
    cancelCreateBtn.type = "button";
    const createError = makeElement("span", "minimax-project-error");
    createGroup.append(nameInput, createBtn, cancelCreateBtn, createError);

    searchRow.append(newBtn, createGroup, searchInput, sortSelect, sortDirBtn, columnsSelect);

    const deleteRow = makeElement("div", "minimax-project-confirm");
    deleteRow.hidden = true;
    const confirmCard = makeElement("div", "minimax-project-confirm-card");
    const confirmTitle = makeElement("span", "minimax-project-confirm-title");
    const deleteText = makeElement("span", "minimax-project-confirm-text");
    const deleteBtn = makeElement("button", "minimax-clip-bin-danger-btn");
    deleteBtn.type = "button";
    const cancelDeleteBtn = makeElement("button", "minimax-clip-bin-refresh-btn", "✕ 取消");
    cancelDeleteBtn.type = "button";
    const deleteError = makeElement("span", "minimax-clip-bin-new-error");
    const confirmActions = makeElement("div", "minimax-project-confirm-actions");
    confirmActions.append(cancelDeleteBtn, deleteBtn);
    confirmCard.append(confirmTitle, deleteText, confirmActions, deleteError);
    deleteRow.appendChild(confirmCard);

    const grid = makeElement("div", "minimax-project-grid");
    const modalHint = makeElement("span", "minimax-project-modal-hint");
    modalHint.textContent = "点卡片切换项目 · ✎ 重命名会移动整个文件夹 · 🗑 删除会清空整个库。";
    modal.append(head, searchRow, grid, modalHint, deleteRow);
    overlay.appendChild(modal);

    document.body.appendChild(overlay);
    // The popup sits above the canvas; keep its pointer events from panning or
    // zooming the graph behind it.
    for (const type of ["pointerdown", "mousedown", "click", "dblclick", "wheel"]) {
        overlay.addEventListener(type, event => event.stopPropagation(), { signal });
    }

    function currentName() {
        const raw = widget?.value;
        return typeof raw === "string" && raw.trim() ? raw.trim() : DEFAULT_PROJECT;
    }

    function rawCount(bin, field) {
        const value = Number(bin?.[field]);
        return Number.isFinite(value) && value > 0 ? value : 0;
    }

    function countTextFor(bin) {
        const total = rawCount(bin, mode === "builder" ? "videos" : "clips");
        return total ? `共 ${config.count(total)}` : config.empty;
    }

    function updatedValue(bin) {
        const raw = String(bin?.updated_at ?? "").trim();
        if (!raw) return 0;
        const stamp = Date.parse(raw.replace(" ", "T"));
        return Number.isFinite(stamp) ? stamp : 0;
    }

    function sortedBins() {
        const list = bins.slice();
        list.sort((a, b) => {
            if (sortField === "updated") {
                const diff = updatedValue(a) - updatedValue(b);
                if (diff) return diff;
            }
            return a.name.localeCompare(b.name, "zh-Hans-CN", {
                numeric: true,
                sensitivity: "base",
            });
        });
        if (sortDir === "desc") list.reverse();
        return list;
    }

    function saveSort() {
        try {
            localStorage.setItem(sortStoreKey, JSON.stringify({ field: sortField, dir: sortDir }));
        } catch (_) {
            // Preference storage is optional.
        }
    }

    function syncSortUi() {
        sortSelect.value = sortField;
        sortDirBtn.textContent = sortDir === "asc" ? "↑" : "↓";
        sortDirBtn.title = sortDir === "asc" ? "当前正序，点击切换为倒序" : "当前倒序，点击切换为正序";
    }

    function saveColumns() {
        try {
            localStorage.setItem(columnsStoreKey, String(projectColumns));
        } catch (_) {
            // Preference storage is optional.
        }
    }

    function applyColumns() {
        grid.style.setProperty("--project-cols", String(projectColumns));
        columnsSelect.value = String(projectColumns);
    }

    function deleteWarning(name, bin) {
        const cards = rawCount(bin, "clips");
        const videos = rawCount(bin, "videos");
        if (!cards) return `删除「${name}」会删掉这个空的素材库文件夹，此操作不可撤销。`;
        const detail = videos
            ? `${cards} 张卡片（含 ${videos} 个已保存的视频文件）`
            : `${cards} 张卡片`;
        return `删除「${name}」会同时删掉 ${detail}，此操作不可撤销。`;
    }

    function makeCover(bin) {
        const box = makeElement("div", "minimax-project-cover");
        if (bin?.cover_url) {
            const image = document.createElement("img");
            image.loading = "lazy";
            image.decoding = "async";
            image.alt = "";
            image.src = bin.cover_url;
            image.onerror = () => {
                image.remove();
                box.appendChild(makeElement("span", "minimax-project-cover-icon", config.coverIcon));
            };
            box.appendChild(image);
        } else {
            box.appendChild(makeElement("span", "minimax-project-cover-icon", config.coverIcon));
        }
        return box;
    }

    function paintCurrent() {
        const active = currentName();
        const bin = bins.find(item => item.name === active)
            || { name: active, clips: 0, videos: 0, cover_url: "", updated_at: "" };
        const paintKey = JSON.stringify([active, bin]);
        if (paintKey === currentPaintKey) return;
        currentPaintKey = paintKey;
        currentCover.textContent = "";
        currentCover.appendChild(makeCover(bin));
        currentNameText.textContent = active;
        projectCount.textContent = countTextFor(bin);
        const updated = fullTime(bin.updated_at);
        currentUpdated.textContent = updated ? `更新 ${updated}` : "";
        currentUpdated.title = updated ? `最后修改：${updated}` : "";
        currentUpdated.hidden = !updated;
        currentCard.title = `${config.labelTitle}：当前「${active}」`;
    }

    function makeAction(label, titleText, handler) {
        const button = makeElement("button", "minimax-project-action", label);
        button.type = "button";
        button.title = titleText;
        button.onclick = (event) => {
            event.preventDefault();
            event.stopPropagation();
            handler();
        };
        return button;
    }

    function renderTile(bin) {
        const tile = makeElement("div", "minimax-project-tile");
        tile.tabIndex = 0;
        tile.setAttribute("role", "button");
        tile.dataset.name = bin.name;
        if (bin.name === currentName()) tile.classList.add("active");
        tile.appendChild(makeCover(bin));

        const body = makeElement("div", "minimax-project-tile-body");
        if (editingName === bin.name) {
            const input = document.createElement("input");
            input.type = "text";
            input.className = "minimax-project-rename-input";
            input.value = bin.name;
            const error = makeElement("span", "minimax-clip-bin-new-error");
            const actions = makeElement("div", "minimax-project-rename-actions");
            const save = makeElement("button", "minimax-clip-bin-refresh-btn", "✔ 保存");
            save.type = "button";
            const cancel = makeElement("button", "minimax-clip-bin-refresh-btn", "✕");
            cancel.type = "button";
            save.onclick = (event) => {
                event.preventDefault();
                event.stopPropagation();
                void commitRename(bin.name, input.value, error, save);
            };
            cancel.onclick = (event) => {
                event.preventDefault();
                event.stopPropagation();
                editingName = "";
                renderGrid();
            };
            input.onkeydown = (event) => {
                event.stopPropagation();
                if (event.key === "Enter") {
                    event.preventDefault();
                    void commitRename(bin.name, input.value, error, save);
                }
                if (event.key === "Escape") {
                    event.preventDefault();
                    editingName = "";
                    renderGrid();
                }
            };
            actions.append(save, cancel);
            body.append(input, actions, error);
        } else {
            body.appendChild(makeElement("span", "minimax-project-tile-name", bin.name));
            const meta = makeElement("div", "minimax-project-tile-meta");
            meta.appendChild(makeElement("span", "minimax-project-tile-count", countTextFor(bin)));
            const updated = fullTime(bin.updated_at);
            if (updated) {
                const time = makeElement("span", "minimax-project-tile-time", updated);
                time.title = `最后修改：${updated}`;
                meta.appendChild(time);
            }
            body.appendChild(meta);
            const actions = makeElement("div", "minimax-project-actions");
            actions.append(
                makeAction("✎", "重命名这个项目", () => {
                    pendingDelete = "";
                    editingName = bin.name;
                    renderGrid();
                }),
                makeAction("🗑", "删除这个项目", () => {
                    editingName = "";
                    showDeleteConfirm(bin);
                }),
            );
            body.appendChild(actions);
        }
        tile.appendChild(body);

        tile.onclick = (event) => {
            if (event.target.closest("button, input")) return;
            void chooseProject(bin.name);
        };
        tile.onkeydown = (event) => {
            if (event.target !== tile) return;
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                void chooseProject(bin.name);
            }
        };
        return tile;
    }

    function renderGrid() {
        const needle = search.trim().toLowerCase();
        const ordered = sortedBins();
        const filtered = needle
            ? ordered.filter(bin => bin.name.toLowerCase().includes(needle))
            : ordered;
        grid.textContent = "";
        modalCount.textContent = `${bins.length} 个库`;
        if (!filtered.length) {
            grid.appendChild(makeElement("div", "minimax-project-empty",
                bins.length ? "没有匹配的项目。" : "还没有项目，点「＋ 新建项目」开始。"));
            return;
        }
        const fragment = document.createDocumentFragment();
        filtered.forEach(bin => fragment.appendChild(renderTile(bin)));
        grid.appendChild(fragment);
        if (editingName) {
            const input = grid.querySelector(".minimax-project-rename-input");
            if (input) requestAnimationFrame(() => {
                input.focus();
                input.select();
            });
        }
    }

    function resetCreateInput() {
        nameInput.value = "";
        showCreateError("");
        syncCreateButtons();
        nameInput.blur();
    }

    function syncCreateButtons() {
        const ready = nameInput.value.trim().length > 0;
        createBtn.disabled = !ready;
        cancelCreateBtn.disabled = !ready;
    }

    function showCreateError(message) {
        createError.textContent = message;
        createError.title = message;
    }

    function closeDeleteRow() {
        deleteRow.hidden = true;
        pendingDelete = "";
        deleteError.textContent = "";
    }

    function openModal() {
        if (openMenuClose && openMenuClose !== closeModal) openMenuClose();
        openMenuClose = closeModal;
        modalOpen = true;
        overlay.hidden = false;
        searchInput.value = search;
        resetCreateInput();
        closeDeleteRow();
        editingName = "";
        renderGrid();
        void refresh();
    }

    function closeModal() {
        modalOpen = false;
        overlay.hidden = true;
        editingName = "";
        pendingDelete = "";
        resetCreateInput();
        closeDeleteRow();
        if (openMenuClose === closeModal) openMenuClose = null;
    }

    currentCard.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        openModal();
    };

    const OPEN_DIR_LABEL = "📂 打开本地目录";
    const OPEN_DIR_TITLE = "在资源管理器中打开当前项目的素材库文件夹";
    let openDirTimer = 0;
    function flashOpenDir(text, tip) {
        openDirBtn.textContent = text;
        openDirBtn.title = tip;
        window.clearTimeout(openDirTimer);
        openDirTimer = window.setTimeout(() => {
            openDirBtn.textContent = OPEN_DIR_LABEL;
            openDirBtn.title = OPEN_DIR_TITLE;
        }, 2600);
    }

    openDirBtn.onclick = async (event) => {
        event.preventDefault();
        event.stopPropagation();
        const project = currentName();
        openDirBtn.disabled = true;
        try {
            const res = await api.fetchApi("/minimax/clip_bin/project/open", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                flashOpenDir("⚠ 打不开目录", data.error || `打开失败（HTTP ${res.status}）`);
                return;
            }
            flashOpenDir("📂 已打开", `已在资源管理器中打开「${project}」`);
        } catch (error) {
            console.warn("[Clip Bin] open project folder failed:", error);
            flashOpenDir("⚠ 打不开目录", "打开失败：连不上后台服务。");
        } finally {
            openDirBtn.disabled = false;
        }
    };

    closeBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        closeModal();
    };
    overlay.onclick = (event) => {
        if (event.target === overlay) closeModal();
    };
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !modalOpen) return;
        event.stopPropagation();
        if (!deleteRow.hidden) {
            closeDeleteRow();
            return;
        }
        closeModal();
    }, { signal });

    searchInput.oninput = () => {
        search = searchInput.value;
        renderGrid();
    };
    sortSelect.onchange = () => {
        sortField = sortSelect.value === "updated" ? "updated" : "name";
        saveSort();
        syncSortUi();
        renderGrid();
    };
    sortDirBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        sortDir = sortDir === "asc" ? "desc" : "asc";
        saveSort();
        syncSortUi();
        renderGrid();
    };
    columnsSelect.onchange = () => {
        const next = parseInt(columnsSelect.value, 10);
        if (next >= 3 && next <= 6) {
            projectColumns = next;
            saveColumns();
            applyColumns();
        }
    };
    newBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        closeDeleteRow();
        nameInput.focus();
        nameInput.select();
    };
    cancelCreateBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        resetCreateInput();
    };
    createBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        void createProject();
    };
    nameInput.oninput = syncCreateButtons;
    nameInput.onkeydown = (event) => {
        event.stopPropagation();
        if (event.key === "Enter") {
            event.preventDefault();
            void createProject();
        }
        if (event.key === "Escape") resetCreateInput();
    };

    function showDeleteConfirm(bin) {
        pendingDelete = bin.name;
        resetCreateInput();
        confirmTitle.textContent = `删除项目「${bin.name}」`;
        deleteText.textContent = deleteWarning(bin.name, bin);
        deleteBtn.textContent = `✔ 删除「${bin.name}」`;
        deleteError.textContent = "";
        deleteRow.hidden = false;
        cancelDeleteBtn.focus();
    }

    cancelDeleteBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        closeDeleteRow();
    };
    deleteBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        void deleteProject();
    };

    async function refreshBins() {
        let list = [];
        try {
            list = (await fetchProjectBins(config.listUrl)).slice();
        } catch (error) {
            if (!signal.aborted) console.warn("[Clip Bin] projects lookup failed:", error);
        }
        if (signal.aborted) return;

        const active = currentName();
        if (!list.some(bin => bin.name === active)) {
            list.unshift({ name: active, clips: 0, videos: 0, cover_url: "", updated_at: "" });
        }
        const changed = JSON.stringify(list) !== JSON.stringify(bins);
        bins = list;
        paintCurrent();
        if (modalOpen && !editingName && changed) renderGrid();
    }

    function refresh() {
        if (!inFlight) {
            inFlight = refreshBins().finally(() => { inFlight = null; });
        }
        return inFlight;
    }

    async function setProject(name, closeAfter = false) {
        resetCreateInput();
        closeDeleteRow();
        editingName = "";
        if (widget) {
            widget.value = name;
            widget.callback?.(name);
            node.setDirtyCanvas?.(true, true);
        }
        await refresh();
        if (closeAfter) closeModal();
    }

    async function chooseProject(name) {
        if (!name) return;
        if (name === currentName()) {
            closeModal();
            return;
        }
        await setProject(name, true);
    }

    async function createProject() {
        const typed = nameInput.value.trim();
        if (!typed) {
            showCreateError("先写个名字。");
            nameInput.focus();
            return;
        }
        createBtn.disabled = true;
        cancelCreateBtn.disabled = true;
        showCreateError("");
        try {
            const res = await api.fetchApi("/minimax/clip_bin/project", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: typed }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                showCreateError(data.error || `建立失败（HTTP ${res.status}）`);
                return;
            }
            await setProject(data.name || typed, true);
        } catch (error) {
            console.warn("[Clip Bin] create project failed:", error);
            showCreateError("建立失败：连不上后台服务。");
        } finally {
            syncCreateButtons();
        }
    }

    async function commitRename(oldName, value, error, saveButton) {
        const typed = value.trim();
        if (!typed) {
            error.textContent = "先写个名字。";
            return;
        }
        if (typed === oldName) {
            editingName = "";
            renderGrid();
            return;
        }
        saveButton.disabled = true;
        error.textContent = "";
        try {
            const res = await api.fetchApi("/minimax/clip_bin/project/rename", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: oldName, new_name: typed }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                error.textContent = data.error || `重命名失败（HTTP ${res.status}）`;
                return;
            }
            const newName = data.name || typed;
            const wasCurrent = currentName() === oldName;
            editingName = "";
            if (wasCurrent) await setProject(newName, false);
            else await refresh();
        } catch (err) {
            console.warn("[Clip Bin] rename project failed:", err);
            error.textContent = "重命名失败：连不上后台服务。";
        } finally {
            saveButton.disabled = false;
        }
    }

    function nextProjectAfter(name) {
        const remaining = bins.map(item => item.name).filter(item => item && item !== name);
        if (remaining.includes(DEFAULT_PROJECT)) return DEFAULT_PROJECT;
        return remaining[0] || DEFAULT_PROJECT;
    }

    async function deleteProject() {
        const name = pendingDelete;
        if (!name) return;
        deleteBtn.disabled = true;
        deleteError.textContent = "";
        try {
            const res = await api.fetchApi("/minimax/clip_bin/project/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: name, confirm: name }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                deleteError.textContent = data.error || `删除失败（HTTP ${res.status}）`;
                return;
            }
            const wasCurrent = currentName() === name;
            pendingDelete = "";
            deleteRow.hidden = true;
            if (wasCurrent) await setProject(nextProjectAfter(name), true);
            else await refresh();
        } catch (error) {
            console.warn("[Clip Bin] delete project failed:", error);
            deleteError.textContent = "删除失败：连不上后台服务。";
        } finally {
            deleteBtn.disabled = false;
        }
    }

    signal.addEventListener("abort", () => {
        window.clearTimeout(openDirTimer);
        overlay.remove();
        if (openMenuClose === closeModal) openMenuClose = null;
    }, { once: true });

    syncSortUi();
    applyColumns();
    syncCreateButtons();
    paintCurrent();
    void refresh();

    return { element: root, refresh, name: currentName };
}
