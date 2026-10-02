// Long Builder panel: choose the shots by card instead of typing ids, get one film back.
//
// The node itself only needs a project name and the list of switched-off cards, so
// this panel is a view over the same two widgets the Clip Bin Picker uses:
// - a project dropdown fed by /minimax/clip_bin/projects (bins with archived video only)
// - a card deck ordered by shot number, one click leaves a take out
// - a summary line that says exactly what will be joined, and why anything is skipped
import { addPanel } from "./dom_panel.js";
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
    }
});

// Mirrors long_builder.shot_number: the first number in a tag is the timeline position.
function shotNumber(tag) {
    const match = /(\d+)/.exec(String(tag || ""));
    return match ? parseInt(match[1], 10) : null;
}

function sortCards(cards) {
    return [...cards].sort((a, b) => {
        const na = shotNumber(a.shot_tag);
        const nb = shotNumber(b.shot_tag);
        if ((na === null) !== (nb === null)) return na === null ? 1 : -1;
        if (na !== null && nb !== null && na !== nb) return na - nb;
        return String(a.created_at || "").localeCompare(String(b.created_at || ""))
            || String(a.clip_id || "").localeCompare(String(b.clip_id || ""));
    });
}

function parseExcluded(text) {
    return String(text || "").split(/[,\n;]+/).map(part => part.trim()).filter(Boolean);
}

function setupLongBuilderPanel(node) {
    const projectWidget = node.widgets?.find(w => w.name === "project_name");
    const excludeWidget = node.widgets?.find(w => w.name === "exclude_clips");

    const container = document.createElement("div");
    container.className = "minimax-clip-bin-container h3-lb-container";

    const header = document.createElement("div");
    header.className = "minimax-clip-bin-header";
    const title = document.createElement("span");
    title.className = "minimax-clip-bin-title h3-lb-title";
    title.textContent = "🎬 长视频拼接";
    const projectSelect = document.createElement("select");
    projectSelect.className = "h3-lb-project";
    projectSelect.title = "选择包含视频文件的项目文件夹";
    const refreshBtn = document.createElement("button");
    refreshBtn.className = "minimax-clip-bin-refresh-btn";
    refreshBtn.textContent = "🔄 刷新";
    header.appendChild(title);
    header.appendChild(projectSelect);
    header.appendChild(refreshBtn);
    container.appendChild(header);

    const summary = document.createElement("div");
    summary.className = "h3-lb-summary";
    container.appendChild(summary);

    const deck = document.createElement("div");
    deck.className = "minimax-clip-bin-deck h3-lb-deck";
    container.appendChild(deck);

    const footer = document.createElement("div");
    footer.className = "h3-lb-footer";
    footer.textContent = "运行后在这里显示成片位置，节点上可直接预览。";
    container.appendChild(footer);

    const { signal } = addPanel(node, "h3_long_builder", container, 260);
    const previewCleanups = new Set();
    const releasePreviews = () => {
        for (const cleanup of previewCleanups) cleanup();
        previewCleanups.clear();
    };
    signal.addEventListener("abort", releasePreviews, { once: true });

    const currentProject = () => (projectWidget?.value || "Default_Project");
    const excluded = () => new Set(parseExcluded(excludeWidget?.value));

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

    async function loadProjects() {
        let names = [];
        try {
            const res = await api.fetchApi("/minimax/clip_bin/projects", { cache: "no-store" });
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

    function describe(cards, offSet) {
        const usable = cards.filter(card => card.has_video);
        const joined = usable.filter(card => !offSet.has(card.clip_id));
        const names = joined.map(card => card.shot_tag || card.clip_id);
        const shown = names.length <= 8 ? names.join(" → ") : names.slice(0, 8).join(" → ") + " …";
        const lines = [];
        lines.push(joined.length
            ? `将拼接 ${joined.length} 段：${shown}`
            : "没有可拼接的片段：卡片全被排除，或都没有归档视频");
        const offCount = usable.length - joined.length;
        if (offCount) lines.push(`已排除 ${offCount} 段（点卡片可加回来）`);
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
        return { joined, usable };
    }

    let requestId = 0;
    async function loadCards() {
        const currentRequest = ++requestId;
        await loadProjects();
        if (signal.aborted || currentRequest !== requestId) return;
        const project = currentProject();
        try {
            const res = await api.fetchApi(`/minimax/clip_bin/list?project=${encodeURIComponent(project)}`,
                { cache: "no-store" });
            if (signal.aborted || currentRequest !== requestId) return;
            releasePreviews();
            deck.innerHTML = "";
            if (!res.ok) {
                summary.innerHTML = "<div>未连接到后台服务，请刷新 ComfyUI 页面后重试。</div>";
                return;
            }
            const data = await res.json();
            const cards = sortCards(data.clips || []);
            const offSet = excluded();
            describe(cards, offSet);

            if (!cards.length) {
                const empty = document.createElement("div");
                empty.className = "h3-lb-empty";
                empty.textContent = "这个项目还没有卡片。先用 Saver 生成并归档几段视频。";
                deck.appendChild(empty);
                return;
            }

            cards.forEach(card => {
                const off = offSet.has(card.clip_id);
                const item = document.createElement("div");
                item.className = "minimax-clip-card h3-lb-card";
                if (off) item.classList.add("h3-lb-off");
                if (!card.has_video) item.classList.add("h3-lb-no-video");

                const thumbWrap = document.createElement("div");
                thumbWrap.className = "minimax-clip-thumb-wrap";
                if (card.thumbnail_url) {
                    const img = document.createElement("img");
                    img.className = "minimax-clip-thumb";
                    img.src = card.thumbnail_url;
                    img.loading = "lazy";
                    img.onerror = () => {
                        thumbWrap.innerHTML = '<div class="minimax-clip-thumb-placeholder">🎬</div>';
                    };
                    thumbWrap.appendChild(img);
                } else {
                    thumbWrap.innerHTML = '<div class="minimax-clip-thumb-placeholder">🎬</div>';
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
                shotName.title = `${card.shot_tag || ""} (${card.clip_id})`;
                body.appendChild(shotName);
                const metrics = document.createElement("div");
                metrics.className = "minimax-clip-metrics";
                const dur = card.duration_seconds != null ? Number(card.duration_seconds).toFixed(2) + "s" : "";
                metrics.innerHTML = [card.frames ? `${card.frames}帧` : "", dur].filter(Boolean).join(" ") || "<span>—</span>";
                body.appendChild(metrics);
                item.appendChild(body);

                if (card.has_video) {
                    item.onclick = () => {
                        setExcluded(card.clip_id, !off);
                        loadCards();
                    };
                }
                deck.appendChild(item);
            });
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

    if (projectWidget) {
        const original = projectWidget.callback;
        projectWidget.callback = function (v) {
            const r = original ? original.apply(this, arguments) : undefined;
            loadCards();
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
        footer.textContent = `上次输出：${where}`;
    };
    signal.addEventListener("abort", () => {
        api.removeEventListener("minimax/clip_bin/changed", onChanged);
        delete node._h3LongRefresh;
        delete node._h3LongResult;
    }, { once: true });
    loadCards();
}
