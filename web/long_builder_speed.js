export const PLAYBACK_SPEED_OPTIONS = ["1.0x", "0.75x", "0.5x", "custom"];

export function normalizeCustomSpeed(value, fallback = 1.0) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return fallback;
    const rounded = Math.round(numeric * 10) / 10;
    return Math.min(1.0, Math.max(0.1, rounded));
}

export function sourcePlaybackSpeed(option, custom = 1.0) {
    if (String(option || "").toLowerCase() === "custom") {
        return normalizeCustomSpeed(custom);
    }
    const text = String(option || "1.0x").trim().replace(/x$/i, "");
    const value = Number(text);
    return Number.isFinite(value) && value > 0 && value <= 1 ? value : 1.0;
}

export function outputPlaybackSpeed(option, custom = 1.0) {
    return 1 / sourcePlaybackSpeed(option, custom);
}

export function outputFrameRate(baseFps, option, custom = 1.0) {
    const base = Number(baseFps);
    if (!Number.isFinite(base) || base <= 0) return 0;
    return base / sourcePlaybackSpeed(option, custom);
}

export function restoredDuration(seconds, option, custom = 1.0) {
    const duration = Number(seconds);
    if (!Number.isFinite(duration) || duration < 0) return 0;
    return duration * sourcePlaybackSpeed(option, custom);
}

export function speedOptionLabel(option) {
    if (option === "0.75x") return "0.75x → 1.333x";
    if (option === "0.5x") return "0.5x → 2x";
    if (option === "custom") return "custom（自定义）";
    return "1.0x（不恢复）";
}

export function speedDescription(option, custom = 1.0, baseFps = 24.0) {
    const source = sourcePlaybackSpeed(option, custom);
    if (source === 1) return "不恢复原速；参数一致时仍可无损直拷。";
    const outputFps = outputFrameRate(baseFps, option, custom);
    return `切片 ${source.toFixed(2)}x → 成片 ${(1 / source).toFixed(3)}x；自动输出 ${outputFps.toFixed(3)}fps，避免恢复时丢帧；音视频同步，需重编码。`;
}
