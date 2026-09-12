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

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            this.imgs = null;
            setupClipBinPickerWidget(this);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            this.imgs = null;
            return r;
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted ? onExecuted.apply(this, arguments) : undefined;
            // Prevent ComfyUI from displaying default preview image in this picker node
            this.imgs = null;
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
    titleWrap.innerHTML = `🎞️ MiniMax Project Clip Bin: <span class="minimax-clip-bin-project-tag">${projectWidget?.value || "Default_Project"}</span>`;

    const actionsWrap = document.createElement("div");
    actionsWrap.className = "minimax-clip-bin-actions";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "minimax-clip-bin-refresh-btn";
    refreshBtn.innerText = "🔄 刷新";
    actionsWrap.appendChild(refreshBtn);

    header.appendChild(titleWrap);
    header.appendChild(actionsWrap);
    container.appendChild(header);

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
    const widget = node.addDOMWidget("clip_bin_gallery", "gallery", container, {
        serialize: false,
        hideOnZoom: false,
    });

    node.imgs = null;

    // Ensure a sensible minimum width for the deck layout
    if (node.size[0] < 520) node.setSize([520, node.size[1]]);

    // Fit node height to match content
    // Uses deck.scrollHeight (content height — immune to node-size feedback loop)
    const DECK_MAX = 340; // .minimax-clip-bin-deck max-height

    function fitToContent() {
        const deckH = Math.min(deck.scrollHeight || 0, DECK_MAX);
        if (deckH === 0) return; // no cards rendered yet

        // Standard widgets (project_name, mode, clip_selection, custom_clip_path)
        const stdW = (node.widgets || []).filter(w => w.type !== "custom");
        const stdH = stdW.length * 28; // ~28px each incl. ComfyUI spacing

        // Chrome: container padding(16) + border(2) + margins(8) + header(~30) + footer(~28)
        //        + ComfyUI node internal padding + widget gaps ≈ 160px
        const CHROME = 160;

        const target = Math.max(stdH + deckH + CHROME, 180);
        if (Math.abs(node.size[1] - target) > 3) node.setSize([node.size[0], target]);
    }

    // Function to open full-featured audio/video modal preview
    function openVideoModal(clip, projectName) {
        const existing = document.getElementById("minimax-video-modal-overlay");
        if (existing) existing.remove();

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
            video.src = "";
            overlay.classList.add("closing");
            setTimeout(() => overlay.remove(), 180);
            window.removeEventListener("keydown", onKeyDown);
        }

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
    async function loadClips() {
        const currentProject = projectWidget?.value || "Default_Project";
        const currentSelection = (selectionWidget?.value || "latest").trim();
        titleWrap.innerHTML = `🎞️ MiniMax Project Clip Bin: <span class="minimax-clip-bin-project-tag">${currentProject}</span>`;

        try {
            const res = await api.fetchApi(`/minimax/clip_bin/list?project=${encodeURIComponent(currentProject)}`);
            if (!res.ok) {
                deck.innerHTML = `<div style="padding: 10px; color: #94a3b8; font-size: 11px;">未连接到后台服务或素材库为空</div>`;
                return;
            }
            const data = await res.json();
            const clips = data.clips || [];

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

                        card.addEventListener("mouseenter", () => {
                            hoverTimer = setTimeout(() => {
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

                        card.addEventListener("mouseleave", () => {
                            if (hoverTimer) {
                                clearTimeout(hoverTimer);
                                hoverTimer = null;
                            }
                            if (hoverVideo) {
                                hoverVideo.pause();
                                hoverVideo.style.opacity = "0";
                                const vRef = hoverVideo;
                                hoverVideo = null;
                                setTimeout(() => {
                                    if (vRef && vRef.parentNode) {
                                        vRef.remove();
                                    }
                                }, 200);
                            }
                        });

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

    // Initial load
    setTimeout(loadClips, 200);

    // Auto-refresh when generation execution finishes
    api.addEventListener("executed", (e) => {
        if (e.detail?.node === String(node.id) || e.detail?.output?.ui?.images) {
            setTimeout(loadClips, 500);
        }
    });

    api.addEventListener("status", (e) => {
        if (e.detail?.exec_info?.queue_remaining === 0) {
            setTimeout(loadClips, 600);
        }
    });
}
