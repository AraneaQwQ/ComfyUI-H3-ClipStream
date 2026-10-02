// Modified by RAFOLIE 2026-09-28: Nodes 2.0 DOM layout and lifecycle.
import { addDeleteButton } from "./delete_button.js";
import { addPanel } from "./dom_panel.js";
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/**
 * MiniMax H3 Clip Bin - Visual Non-Linear Timeline & Interactive Card Deck Extension.
 *
 * Implements:
 * - Horizontal carousel of clip cards directly inside MiniMaxClipBinPicker node.
 * - Thumbnail previews (First Frame & Tail Handover Frame).
 * - Click-to-select active continuation source (highlights card, syncs clip_selection widget).
 * - Special Auto / Initial mode card.
 * - Auto-refresh on generation completion.
 */

// Inject CSS stylesheet into page header
const styleId = "minimax-clip-bin-styles";
if (!document.getElementById(styleId)) {
    const link = document.createElement("link");
    link.id = styleId;
    link.rel = "stylesheet";
    link.type = "text/css";
    link.href = new URL("./clip_bin_picker.css", import.meta.url).href;
    document.head.appendChild(link);
}

app.registerExtension({
    name: "MiniMaxH3.ClipBinPicker",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "MiniMaxClipBinPicker" && nodeData.name !== "MiniMaxClipBinDualPicker") {
            return;
        }

        // Prevent node from shrinking below one card's display size
        nodeType.prototype.min_size = [320, 200];

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            this.imgs = null;
            // Force minimum size so cards are always visible
            if (this.size[0] < 320 || this.size[1] < 200) {
                this.setSize([Math.max(this.size[0], 320), Math.max(this.size[1], 200)]);
            }
            setupClipBinPickerWidget(this);
            if (nodeData.name === "MiniMaxClipBinDualPicker") {
                // Leave room for seven outputs, controls and the card gallery.
                // Only creation sets this default; saved workflow sizes win later.
                this.setSize([Math.max(this.size[0], 680), Math.max(this.size[1], 640)]);
            }
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            this.imgs = null;
            this._h3ClipRefresh?.();
            return r;
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted ? onExecuted.apply(this, arguments) : undefined;
            // Prevent ComfyUI from displaying default preview image in this picker node
            this.imgs = null;
            this._h3ClipRefresh?.();
            return r;
        };

        nodeType.prototype.setSizeForImage = function () {
            // Prevent auto-resizing picker node for image previews
        };
    }
});

function setupClipBinPickerWidget(node) {
    // Find relevant widgets
    const projectWidget = node.widgets?.find(w => w.name === "project_name");
    const selectionWidget = node.widgets?.find(w => w.name === "clip_selection");

    // Container DOM
    const container = document.createElement("div");
    container.className = "minimax-clip-bin-container";

    // Header
    const header = document.createElement("div");
    header.className = "minimax-clip-bin-header";

    const titleWrap = document.createElement("div");
    titleWrap.className = "minimax-clip-bin-title";
    const titleText = document.createElement("span");
    titleText.textContent = "🎞️ MiniMax Project Clip Bin:";
    // The bin is picked from the folders that actually exist, and the first entry in
    // the menu starts a new one, so no name ever has to be typed from memory.
    const projectSelect = document.createElement("select");
    projectSelect.className = "minimax-clip-bin-project";
    projectSelect.title = "选择素材库，或新建一个";
    titleWrap.appendChild(titleText);
    titleWrap.appendChild(projectSelect);

    const actionsWrap = document.createElement("div");
    actionsWrap.className = "minimax-clip-bin-actions";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "minimax-clip-bin-refresh-btn";
    refreshBtn.innerText = "🔄 刷新";
    actionsWrap.appendChild(refreshBtn);

    // Zoom controls
    const zoomLabel = document.createElement("span");
    zoomLabel.className = "minimax-clip-bin-zoom-label";
    zoomLabel.textContent = "100%";
    const btnZoomIn = document.createElement("button");
    btnZoomIn.className = "minimax-clip-bin-refresh-btn";
    btnZoomIn.textContent = "+";
    btnZoomIn.title = "放大卡片";
    const btnZoomOut = document.createElement("button");
    btnZoomOut.className = "minimax-clip-bin-refresh-btn";
    btnZoomOut.textContent = "−";
    btnZoomOut.title = "缩小卡片";
    actionsWrap.appendChild(btnZoomOut);
    actionsWrap.appendChild(zoomLabel);
    actionsWrap.appendChild(btnZoomIn);

    header.appendChild(titleWrap);
    header.appendChild(actionsWrap);
    container.appendChild(header);

    const createRow = document.createElement("div");
    createRow.className = "minimax-clip-bin-new";
    createRow.hidden = true;
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "minimax-clip-bin-new-input";
    nameInput.placeholder = "新项目名（例如：科幻短片 01）";
    const createBtn = document.createElement("button");
    createBtn.className = "minimax-clip-bin-refresh-btn";
    createBtn.textContent = "✔ 建立";
    const cancelCreateBtn = document.createElement("button");
    cancelCreateBtn.className = "minimax-clip-bin-refresh-btn";
    cancelCreateBtn.textContent = "✕ 取消";
    const createError = document.createElement("span");
    createError.className = "minimax-clip-bin-new-error";
    createRow.appendChild(nameInput);
    createRow.appendChild(createBtn);
    createRow.appendChild(cancelCreateBtn);
    createRow.appendChild(createError);
    container.appendChild(createRow);

    // Deleting a bin is the mirror of creating one, so it lives in the same menu. It
    // takes the whole story with it, so the confirm button repeats the name.
    const deleteRow = document.createElement("div");
    deleteRow.className = "minimax-clip-bin-new minimax-clip-bin-danger";
    deleteRow.hidden = true;
    const deleteText = document.createElement("span");
    deleteText.className = "minimax-clip-bin-danger-text";
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "minimax-clip-bin-danger-btn";
    const cancelDeleteBtn = document.createElement("button");
    cancelDeleteBtn.className = "minimax-clip-bin-refresh-btn";
    cancelDeleteBtn.textContent = "✕ 取消";
    const deleteError = document.createElement("span");
    deleteError.className = "minimax-clip-bin-new-error";
    deleteRow.appendChild(deleteText);
    deleteRow.appendChild(deleteBtn);
    deleteRow.appendChild(cancelDeleteBtn);
    deleteRow.appendChild(deleteError);
    container.appendChild(deleteRow);
    // --- Card Zoom State ---
    const ZOOM_STEPS = [1, 1.5, 2, 3, 4]; // 100%, 150%, 200%, 300%, 400%
    let zoomIdx = 0;
    const BASE_CARD_MIN = 150; // px
    const BASE_THUMB_H = 85;   // px

    function applyCardZoom() {
        const z = ZOOM_STEPS[zoomIdx];
        const cardMin = Math.round(BASE_CARD_MIN * z);
        const thumbH = Math.round(BASE_THUMB_H * z);
        container.style.setProperty("--card-min", cardMin + "px");
        container.style.setProperty("--thumb-h", thumbH + "px");
        zoomLabel.textContent = Math.round(z * 100) + "%";
        requestAnimationFrame(fitToContent);
    }

    btnZoomIn.onclick = (e) => {
        e.stopPropagation();
        if (zoomIdx < ZOOM_STEPS.length - 1) { zoomIdx++; applyCardZoom(); }
    };
    btnZoomOut.onclick = (e) => {
        e.stopPropagation();
        if (zoomIdx > 0) { zoomIdx--; applyCardZoom(); }
    };

    // Deck carousel
    const deck = document.createElement("div");
    deck.className = "minimax-clip-bin-deck";
    container.appendChild(deck);

    // Footer bar
    const footer = document.createElement("div");
    footer.className = "minimax-clip-bin-footer";
    const selectionInfo = document.createElement("div");
    selectionInfo.className = "minimax-clip-bin-selection-info";
    selectionInfo.innerHTML = `选中镜头: <span class="minimax-clip-bin-selected-target">${selectionWidget?.value || "latest"}</span>`;

    const hintText = document.createElement("div");
    hintText.innerText = "👉 点选片段作为接续源";
    footer.appendChild(selectionInfo);
    footer.appendChild(hintText);
    container.appendChild(footer);

    // Add DOM widget to node
    const { signal } = addPanel(node, "clip_bin_gallery", container);

    node.imgs = null;

    // Ensure a sensible minimum width for the deck layout
    if (node.size[0] < 520) node.setSize([520, node.size[1]]);

    // Fit node height: shrink so bottom edge flush with container bottom
    function fitToContent() {
        // Nodes 2.0 and Canvas allocate the DOM widget height; keep user sizing.
        node.setDirtyCanvas?.(true, true);
    }

    // Function to open full-featured audio/video modal preview
    function openVideoModal(clip, projectName) {
        const existing = document.getElementById("minimax-video-modal-overlay");
        if (existing) existing._h3Close?.();

        const overlay = document.createElement("div");
        overlay.id = "minimax-video-modal-overlay";
        overlay.className = "minimax-video-modal-overlay";

        const modal = document.createElement("div");
        modal.className = "minimax-video-modal";

        // Modal Header
        const mHeader = document.createElement("div");
        mHeader.className = "minimax-modal-header";
        mHeader.innerHTML = `
            <div class="minimax-modal-title">
                <span class="minimax-modal-shot-title">🎬 ${clip.shot_tag || "Shot"}</span>
                <span class="minimax-modal-clip-id">${clip.clip_id}</span>
            </div>
            <button class="minimax-modal-close-btn" title="关闭 (Esc)">✕</button>
        `;

        // Modal Body
        const mBody = document.createElement("div");
        mBody.className = "minimax-modal-body";

        const videoWrap = document.createElement("div");
        videoWrap.className = "minimax-modal-video-wrap";
        const video = document.createElement("video");
        video.className = "minimax-modal-video";
        video.src = clip.video_url;
        video.controls = true;
        video.autoplay = true;
        video.playsInline = true;
        videoWrap.appendChild(video);

        const metaPanel = document.createElement("div");
        metaPanel.className = "minimax-modal-meta";
        metaPanel.innerHTML = `
            <div class="minimax-modal-meta-title">镜头属性看板</div>
            <div class="minimax-modal-row">
                <span class="label">归属项目:</span>
                <span class="value">${projectName}</span>
            </div>
            ${(() => {
                if (clip.variants) {
                    const rows = Object.entries(clip.variants)
                        .filter(([, v]) => v && v.has_latent)
                        .map(([label, v]) => `
                            <div class="minimax-modal-row">
                                <span class="label">${label} 时长:</span>
                                <span class="value">${v.duration_seconds != null ? Number(v.duration_seconds).toFixed(2) + " 秒" : "?"}${v.frames ? ` (${v.frames} 帧)` : ""}</span>
                            </div>`);
                    return rows.join("") || `<div class="minimax-modal-row"><span class="label">规格参数:</span><span class="value">—</span></div>`;
                }
                const durTxt = clip.duration_seconds != null ? Number(clip.duration_seconds).toFixed(2) + " 秒" : "";
                return `<div class="minimax-modal-row"><span class="label">规格参数:</span><span class="value">${[clip.frames ? `${clip.frames} 帧` : "", durTxt, `${clip.fps || 24} fps`].filter(Boolean).join(" | ")}</span></div>`;
            })()}
            <div class="minimax-modal-row">
                <span class="label">生成时间:</span>
                <span class="value">${clip.created_at || "未知"}</span>
            </div>
            ${clip.parent_clip_id ? `
            <div class="minimax-modal-row">
                <span class="label">父镜头血缘:</span>
                <span class="value parent-link" title="${clip.parent_clip_id}">${clip.parent_clip_id}</span>
            </div>` : ""}
            ${clip.prompt ? `
            <div class="minimax-modal-prompt-wrap">
                <div class="label">正向描述词 (Prompt):</div>
                <div class="prompt-content">${clip.prompt}</div>
            </div>` : ""}
        `;

        mBody.appendChild(videoWrap);
        mBody.appendChild(metaPanel);

        // Modal Footer
        const mFooter = document.createElement("div");
        mFooter.className = "minimax-modal-footer";

        const selectBtn = document.createElement("button");
        selectBtn.className = "minimax-modal-select-btn";
        selectBtn.innerHTML = `🎯 设为当前接续源 (Select Context)`;
        selectBtn.onclick = () => {
            if (selectionWidget) {
                selectionWidget.value = clip.clip_id;
                selectionWidget.callback?.(selectionWidget.value);
            }
            updateSelectionDisplay(clip.shot_tag ? `${clip.shot_tag} (${clip.clip_id.slice(-8)})` : clip.clip_id);
            closeModal();
            loadClips();
        };

        const closeBtn = document.createElement("button");
        closeBtn.className = "minimax-modal-cancel-btn";
        closeBtn.innerText = "关闭";
        closeBtn.onclick = closeModal;

        mFooter.appendChild(selectBtn);
        mFooter.appendChild(closeBtn);

        modal.appendChild(mHeader);
        modal.appendChild(mBody);
        modal.appendChild(mFooter);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        function closeModal() {
            video.pause();
            video.removeAttribute("src");
            video.load();
            overlay.remove();
            window.removeEventListener("keydown", onKeyDown);
            signal.removeEventListener("abort", closeModal);
        }
        overlay._h3Close = closeModal;
        signal.addEventListener("abort", closeModal, { once: true });

        function onKeyDown(e) {
            if (e.key === "Escape") {
                closeModal();
            }
        }
        window.addEventListener("keydown", onKeyDown);

        mHeader.querySelector(".minimax-modal-close-btn").onclick = closeModal;
        overlay.onclick = (e) => {
            if (e.target === overlay) closeModal();
        };
    }

    // Function to load and render clips
    const previewCleanups = new Set();
    function releasePreviews() {
        for (const cleanup of previewCleanups) cleanup();
        previewCleanups.clear();
    }
    signal.addEventListener("abort", releasePreviews, { once: true });
    // The menu lists every bin on disk with how much it holds; an empty bin is still
    // a valid place to save the next shot.
    const NEW_PROJECT = "__new__";
    const DELETE_PROJECT = "__delete__";
    let projectBins = [];

    async function loadProjects() {
        let bins = [];
        try {
            const res = await api.fetchApi("/minimax/clip_bin/projects", { cache: "no-store" });
            if (res.ok) {
                bins = (await res.json()).projects || [];
            }
        } catch (e) {
            console.warn("[Clip Bin] projects lookup failed:", e);
        }
        if (signal.aborted) return;
        const active = projectWidget?.value || "Default_Project";
        if (!bins.some(bin => bin.name === active)) {
            bins.unshift({ name: active, clips: 0, videos: 0 });
        }
        projectSelect.innerHTML = "";
        const newOption = document.createElement("option");
        newOption.value = NEW_PROJECT;
        newOption.textContent = "＋ 新建项目…";
        projectSelect.appendChild(newOption);
        for (const bin of bins) {
            const option = document.createElement("option");
            option.value = bin.name;
            option.textContent = bin.clips ? `${bin.name} (${bin.clips} 卡)` : `${bin.name}（空）`;
            if (bin.name === active) option.selected = true;
            projectSelect.appendChild(option);
        }
        const deleteOption = document.createElement("option");
        deleteOption.value = DELETE_PROJECT;
        deleteOption.textContent = "🗑 删除当前项目…";
        projectSelect.appendChild(deleteOption);
        // Keep the counts so the confirm step can say what is about to be lost.
        projectBins = bins;
    }

    let requestId = 0;
    async function loadClips(deletedId = null) {
        if (signal.aborted) return;
        const currentRequest = ++requestId;
        await loadProjects();
        if (signal.aborted || currentRequest !== requestId) return;
        const currentProject = projectWidget?.value || "Default_Project";
        if (deletedId != null && selectionWidget?.value === deletedId) {
            selectionWidget.value = "latest";
            node.setDirtyCanvas?.(true, true);
        }
        const currentSelection = (selectionWidget?.value || "latest").trim();
        updateSelectionDisplay(currentSelection);

        try {
            const res = await api.fetchApi(`/minimax/clip_bin/list?project=${encodeURIComponent(currentProject)}`, { cache: "no-store" });
            if (signal.aborted || currentRequest !== requestId) return;
            if (!res.ok) {
                releasePreviews();
                deck.innerHTML = `<div style="padding: 10px; color: #94a3b8; font-size: 11px;">未连接到后台服务或素材库为空</div>`;
                return;
            }
            const data = await res.json();
            if (signal.aborted || currentRequest !== requestId) return;
            const clips = data.clips || [];

            releasePreviews();
            deck.innerHTML = "";

            // 1. Always append "Auto / Initial" Special Card
            const autoCard = document.createElement("div");
            const isAutoActive = currentSelection.toLowerCase() === "latest" || currentSelection.toLowerCase() === "auto" || currentSelection === "";
            autoCard.className = `minimax-clip-card auto-card ${isAutoActive ? "active" : ""}`;
            autoCard.innerHTML = `
                <div class="minimax-clip-thumb-wrap">
                    <div class="minimax-clip-thumb-placeholder">⚡</div>
                    ${isAutoActive ? '<div class="minimax-clip-active-badge">当前接续源</div>' : ""}
                </div>
                <div class="minimax-clip-body">
                    <div class="minimax-clip-shot-name">✨ Auto / 自动最新</div>
                    <div class="minimax-clip-metrics">
                        <span>首段开辟 / 持续自动</span>
                    </div>
                    <div class="minimax-clip-lineage">智能递推 | 零手动配置</div>
                </div>
            `;
            autoCard.onclick = () => {
                if (selectionWidget) {
                    selectionWidget.value = "latest";
                    selectionWidget.callback?.(selectionWidget.value);
                }
                updateSelectionDisplay("latest");
                loadClips();
            };
            deck.appendChild(autoCard);

            // 2. Render all clips
            if (clips.length === 0) {
                const emptyMsg = document.createElement("div");
                emptyMsg.style.cssText = "padding: 20px 10px; color: #64748b; font-size: 11px; white-space: nowrap;";
                emptyMsg.innerText = "素材库暂无片段，执行生成后将自动收入...";
                deck.appendChild(emptyMsg);
            } else {
                clips.forEach(clip => {
                    const card = document.createElement("div");
                    const isActive = currentSelection === clip.clip_id;
                    card.className = `minimax-clip-card ${isActive ? "active" : ""}`;

                    // Thumbnail
                    const thumbWrap = document.createElement("div");
                    thumbWrap.className = "minimax-clip-thumb-wrap";

                    if (clip.thumbnail_url) {
                        const img = document.createElement("img");
                        img.className = "minimax-clip-thumb";
                        img.src = clip.thumbnail_url;
                        img.loading = "lazy";
                        img.onerror = () => {
                            thumbWrap.innerHTML = `<div class="minimax-clip-thumb-placeholder">🎬</div>`;
                        };
                        thumbWrap.appendChild(img);
                    } else {
                        thumbWrap.innerHTML = `<div class="minimax-clip-thumb-placeholder">🎬</div>`;
                    }

                    // Video badge & play trigger
                    if (clip.has_video && clip.video_url) {
                        const vidBadge = document.createElement("div");
                        vidBadge.className = "minimax-clip-video-badge";
                        vidBadge.innerHTML = "▶ MP4";
                        vidBadge.title = "点击全屏视听播放";
                        vidBadge.onclick = (e) => {
                            e.stopPropagation();
                            openVideoModal(clip, currentProject);
                        };
                        thumbWrap.appendChild(vidBadge);

                        const playOverlay = document.createElement("button");
                        playOverlay.className = "minimax-clip-play-overlay";
                        playOverlay.innerHTML = "▶";
                        playOverlay.title = "视听播放";
                        playOverlay.onclick = (e) => {
                            e.stopPropagation();
                            openVideoModal(clip, currentProject);
                        };
                        thumbWrap.appendChild(playOverlay);

                        // Hover-to-Play dynamic preview (muted, lightweight loop)
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

                        card.addEventListener("mouseenter", () => {
                            if (signal.aborted) return;
                            stopHover();
                            hoverTimer = setTimeout(() => {
                                if (signal.aborted || !card.isConnected) return;
                                if (!hoverVideo) {
                                    hoverVideo = document.createElement("video");
                                    hoverVideo.className = "minimax-clip-hover-video";
                                    hoverVideo.src = clip.video_url;
                                    hoverVideo.muted = true;
                                    hoverVideo.loop = true;
                                    hoverVideo.playsInline = true;
                                    hoverVideo.autoplay = true;
                                    thumbWrap.appendChild(hoverVideo);
                                }
                                hoverVideo.play().catch(() => {});
                                hoverVideo.style.opacity = "1";
                            }, 180);
                        });

                        card.addEventListener("mouseleave", stopHover);

                        // Double click to open full video modal
                        card.ondblclick = (e) => {
                            e.stopPropagation();
                            openVideoModal(clip, currentProject);
                        };
                    }

                    if (isActive) {
                        const badge = document.createElement("div");
                        badge.className = "minimax-clip-active-badge";
                        badge.innerText = "当前接续源";
                        thumbWrap.appendChild(badge);
                    }
                    card.appendChild(thumbWrap);

                    // Body
                    const body = document.createElement("div");
                    body.className = "minimax-clip-body";

                    // Shot tag
                    const shotName = document.createElement("div");
                    shotName.className = "minimax-clip-shot-name";
                    shotName.innerText = clip.shot_tag || "Shot";
                    shotName.title = `${clip.shot_tag} (${clip.clip_id})`;
                    body.appendChild(shotName);

                    // Metrics (real durations: probed from the archived video when available)
                    const metrics = document.createElement("div");
                    metrics.className = "minimax-clip-metrics";
                    if (clip.variants) {
                        const parts = [];
                        for (const [label, v] of Object.entries(clip.variants)) {
                            if (v && v.has_latent) {
                                const durTxt = v.duration_seconds != null ? Number(v.duration_seconds).toFixed(2) + "s" : "?";
                                parts.push(`<span>${label} ${durTxt}</span>`);
                            }
                        }
                        metrics.innerHTML = parts.length ? parts.join("") : `<span>—</span>`;
                    } else {
                        const durTxt = clip.duration_seconds != null ? Number(clip.duration_seconds).toFixed(2) + "s" : "";
                        metrics.innerHTML = [clip.frames ? `${clip.frames}帧` : "", durTxt].filter(Boolean).join(" ") || `<span>—</span>`;
                    }
                    body.appendChild(metrics);

                    // Variant badges (Dual Clip)
                    if (clip.variants) {
                        const variantBar = document.createElement("div");
                        variantBar.className = "minimax-clip-variants";
                        const hasA = clip.variants["一采"]?.has_latent;
                        const hasB = clip.variants["二采"]?.has_latent;
                        if (hasA) variantBar.innerHTML += `<span class="variant-badge variant-a">一采 ✓</span>`;
                        if (hasB) variantBar.innerHTML += `<span class="variant-badge variant-b">二采 ✓</span>`;
                        body.appendChild(variantBar);
                    }

                    // Lineage / Parent
                    if (clip.parent_clip_id) {
                        const lineage = document.createElement("div");
                        lineage.className = "minimax-clip-lineage";
                        lineage.innerText = `↳ 衍生自: ${clip.parent_clip_id.slice(-8)}`;
                        lineage.title = `父镜头: ${clip.parent_clip_id}`;
                        body.appendChild(lineage);
                    }

                    addDeleteButton(body, {
                        description: `项目「${currentProject}」的 ${clip.shot_tag || clip.clip_id}${clip.variants ? "（含一采、二采）" : ""}`,
                        signal,
                        onDelete: async () => {
                            releasePreviews();
                            document.getElementById("minimax-video-modal-overlay")?._h3Close?.();
                            const response = await api.fetchApi("/minimax/clip_bin/delete", {
                                method: "POST", headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ project: currentProject, clip_id: clip.clip_id }),
                            });
                            if (!response.ok) {
                                const error = await response.json().catch(() => ({}));
                                throw new Error(error.error || `删除失败 (${response.status})；请确认已重启 ComfyUI。`);
                            }
                            if (!signal.aborted && (projectWidget?.value || "Default_Project") === currentProject) {
                                await loadClips(clip.clip_id);
                            }
                        },
                    });
                    card.appendChild(body);

                    // Click to select
                    card.onclick = () => {
                        if (selectionWidget) {
                            selectionWidget.value = clip.clip_id;
                            selectionWidget.callback?.(selectionWidget.value);
                        }
                        updateSelectionDisplay(clip.shot_tag ? `${clip.shot_tag} (${clip.clip_id.slice(-8)})` : clip.clip_id);
                        loadClips();
                    };

                    deck.appendChild(card);
                });
            }

            requestAnimationFrame(fitToContent);
        } catch (e) {
            console.warn("[Clip Bin] Error loading clips:", e);
        }
    }

    function updateSelectionDisplay(val) {
        selectionInfo.innerHTML = `选中镜头: <span class="minimax-clip-bin-selected-target">${val}</span>`;
    }

    // Bind refresh button
    refreshBtn.onclick = (e) => {
        e.stopPropagation();
        loadClips();
    };

    // Switching bins goes through the widget so the graph and the deck stay in step.
    function setProject(name) {
        closeCreateRow();
        closeDeleteRow();
        if (!projectWidget) {
            loadClips();
            return;
        }
        projectWidget.value = name;
        projectWidget.callback?.(name);
        node.setDirtyCanvas?.(true, true);
    }

    function openCreateRow() {
        createRow.hidden = false;
        createError.textContent = "";
        nameInput.focus();
    }

    function closeCreateRow() {
        createRow.hidden = true;
        nameInput.value = "";
        createError.textContent = "";
    }

    async function createProject() {
        const typed = nameInput.value.trim();
        if (!typed) {
            createError.textContent = "先写个名字。";
            nameInput.focus();
            return;
        }
        createBtn.disabled = true;
        createError.textContent = "";
        try {
            const res = await api.fetchApi("/minimax/clip_bin/project", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: typed }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                createError.textContent = data.error || `建立失败（HTTP ${res.status}）`;
                return;
            }
            closeCreateRow();
            setProject(data.name || typed);
        } catch (e) {
            console.warn("[Clip Bin] create project failed:", e);
            createError.textContent = "建立失败：连不上后台服务。";
        } finally {
            createBtn.disabled = false;
        }
    }

    projectSelect.onchange = () => {
        const chosen = projectSelect.value;
        if (chosen === NEW_PROJECT) {
            projectSelect.value = projectWidget?.value || "Default_Project";
            openCreateRow();
            return;
        }
        if (chosen === DELETE_PROJECT) {
            projectSelect.value = projectWidget?.value || "Default_Project";
            openDeleteRow();
            return;
        }
        if (chosen && chosen !== (projectWidget?.value || "")) setProject(chosen);
    };
    createBtn.onclick = (e) => {
        e.stopPropagation();
        createProject();
    };
    cancelCreateBtn.onclick = (e) => {
        e.stopPropagation();
        closeCreateRow();
    };
    nameInput.onkeydown = (e) => {
        e.stopPropagation();
        if (e.key === "Enter") createProject();
        if (e.key === "Escape") closeCreateRow();
    };

    function openDeleteRow() {
        const name = projectWidget?.value || "Default_Project";
        const bin = projectBins.find(item => item.name === name) || { clips: 0, videos: 0 };
        deleteText.textContent = `删除「${name}」会同时删掉 ${bin.clips} 张卡片（含 ${bin.videos} 个已保存的视频文件），此操作不可撤销。`;
        deleteBtn.textContent = `✔ 删除「${name}」`;
        deleteRow.dataset.project = name;
        deleteError.textContent = "";
        deleteRow.hidden = false;
    }

    function closeDeleteRow() {
        deleteRow.hidden = true;
        deleteRow.dataset.project = "";
        deleteError.textContent = "";
    }

    // The panel always needs somewhere to point, so after a delete it moves to the
    // default bin when there is one, otherwise to whatever is left.
    function nextProjectAfter(name) {
        const remaining = projectBins.map(item => item.name).filter(item => item && item !== name);
        if (remaining.includes("Default_Project")) return "Default_Project";
        return remaining[0] || "Default_Project";
    }

    async function deleteProject() {
        const name = deleteRow.dataset.project;
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
            closeDeleteRow();
            setProject(nextProjectAfter(name));
        } catch (e) {
            console.warn("[Clip Bin] delete project failed:", e);
            deleteError.textContent = "删除失败：连不上后台服务。";
        } finally {
            deleteBtn.disabled = false;
        }
    }

    deleteBtn.onclick = (e) => {
        e.stopPropagation();
        deleteProject();
    };
    cancelDeleteBtn.onclick = (e) => {
        e.stopPropagation();
        closeDeleteRow();
    };

    // Watch projectWidget changes
    if (projectWidget) {
        const origCallback = projectWidget.callback;
        projectWidget.callback = function (v) {
            const r = origCallback ? origCallback.apply(this, arguments) : undefined;
            loadClips();
            return r;
        };
    }

    // Watch clip_selection changes
    if (selectionWidget) {
        const origSelCallback = selectionWidget.callback;
        selectionWidget.callback = function (v) {
            const r = origSelCallback ? origSelCallback.apply(this, arguments) : undefined;
            updateSelectionDisplay(v);
            loadClips();
            return r;
        };
    }

    const onDeleted = event => {
        if (event.detail?.project === (projectWidget?.value || "Default_Project")) {
            loadClips(event.detail.deleted_id);
        }
    };
    api.addEventListener("minimax/clip_bin/changed", onDeleted);
    signal.addEventListener("abort", () => api.removeEventListener("minimax/clip_bin/changed", onDeleted), { once: true });
    node._h3ClipRefresh = loadClips;
    const onExecuted = () => loadClips();
    api.addEventListener("execution_success", onExecuted);
    signal.addEventListener("abort", () => {
        api.removeEventListener("execution_success", onExecuted);
        delete node._h3ClipRefresh;
    }, { once: true });
    loadClips();
}
