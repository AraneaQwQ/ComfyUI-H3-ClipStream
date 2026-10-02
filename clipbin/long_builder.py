"""Long-video assembly for the Clip Bin media pool.

A project is generated shot by shot and every run appends one card to the bin; the
archived MP4s then have to be stitched together by hand. This module does that
stitching in one pass: it resolves the shot order, reads the video already stored
inside each card, checks that the pieces are actually joinable, and concatenates
them with ffmpeg.

Two rules keep the result honest:

* ``meta.frames`` is a latent-domain number (see
  ``_shared.latent_steps_to_pixel_frames``) and is only used here to detect an
  untrimmed seam. Every number that reaches the output file is measured from the
  file itself with ffprobe.
* Nothing is silently dropped or silently retimed. A missing video, a broken
  lineage, or mismatched stream parameters is reported, and unless the caller
  opted out it raises instead of producing a plausible-looking bad film.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .clip_bin_manager import (
    get_project_dir,
    load_project_index,
    sanitize_project_name,
    _find_ffprobe,
)

logger = logging.getLogger("minimax_clip_bin_long")

# Long films live beside the media pool, never inside a project folder, so the
# index rebuild and the gallery can never mistake them for a card.
LONG_DIR_NAME = "h3_long"

MAX_CHAIN = 200
INITIAL_MARKERS = ("[INITIAL]", "[INITIAL_GENERATION]")

VARIANT_PREFER_UP = "优先二采（无则退回一采）"
VARIANT_ONLY_FIRST = "仅一采"
VARIANT_ONLY_UP = "仅二采"
VARIANT_POLICIES = (VARIANT_PREFER_UP, VARIANT_ONLY_FIRST, VARIANT_ONLY_UP)

JOIN_AUTO = "auto（参数一致无损直拷，否则重编码）"
JOIN_COPY = "copy（只允许无损直拷，参数不一致报错）"
JOIN_REENCODE = "reencode（统一重编码）"
JOIN_MODES = (JOIN_AUTO, JOIN_COPY, JOIN_REENCODE)


def get_output_root() -> str:
    """Returns ComfyUI's output folder; long films are written under it."""
    try:
        import folder_paths
        return folder_paths.get_output_directory()
    except Exception:
        return "output"


def get_long_dir(project_name: str) -> str:
    """Returns and ensures the folder that holds this project's long films."""
    target = os.path.join(get_output_root(), LONG_DIR_NAME, sanitize_project_name(project_name))
    os.makedirs(target, exist_ok=True)
    return target


def list_bin_clips(project_name: str) -> List[Dict[str, Any]]:
    """Returns the project's card metadata, newest first, as stored in the index."""
    index = load_project_index(project_name)
    return [c for c in index.get("clips", []) if isinstance(c, dict) and c.get("clip_id")]


def find_clip(clips: List[Dict[str, Any]], reference: str) -> Optional[Dict[str, Any]]:
    """Resolves a clip_id exactly, or by substring of clip_id/shot_tag (newest match wins)."""
    ref = str(reference or "").strip()
    if not ref:
        return None
    for clip in clips:
        if clip.get("clip_id") == ref:
            return clip
    matched = [c for c in clips
               if ref in str(c.get("clip_id", "")) or ref in str(c.get("shot_tag", ""))]
    return matched[0] if matched else None


def parse_sequence(text: str) -> List[str]:
    """Splits a hand-written shot order into references."""
    return [part.strip() for part in re.split(r"[,\n;]+", str(text or "")) if part.strip()]


def resolve_shot_order(clips: List[Dict[str, Any]],
                       end_ref: str = "latest",
                       start_ref: str = "",
                       sequence_text: str = "") -> Tuple[List[str], List[str]]:
    """Works out which cards to join, oldest first.

    Default is a lineage walk: start at the newest card (or at ``end_ref``) and
    follow ``parent_clip_id`` backwards until ``start_ref``, a card with no parent,
    or a broken link. A hand-written ``sequence_text`` replaces the walk entirely,
    which is what a branched project needs - lineage alone cannot say which
    branch the user wants.

    Returns (clip_ids in join order, warnings).
    """
    warnings: List[str] = []

    if sequence_text and sequence_text.strip():
        ordered = []
        for ref in parse_sequence(sequence_text):
            clip = find_clip(clips, ref)
            if clip is None:
                warnings.append("库里找不到镜头「%s」，已跳过" % ref)
                continue
            ordered.append(clip["clip_id"])
        return ordered, warnings

    if not clips:
        return [], ["项目库是空的，没有可拼接的镜头"]

    if str(end_ref or "").strip().lower() in ("", "latest", "auto", "default"):
        current = clips[0]
    else:
        current = find_clip(clips, end_ref)
        if current is None:
            return [], ["终点镜头「%s」在库里找不到" % end_ref]

    start_id = None
    if str(start_ref or "").strip():
        start_clip = find_clip(clips, start_ref)
        if start_clip is None:
            warnings.append("起点镜头「%s」在库里找不到，改为一直回溯到血缘根部" % start_ref)
        else:
            start_id = start_clip["clip_id"]

    chain: List[str] = []
    seen = set()
    while current is not None:
        clip_id = current["clip_id"]
        if clip_id in seen:
            warnings.append("血缘在「%s」处形成循环，已停止回溯" % clip_id)
            break
        seen.add(clip_id)
        chain.append(clip_id)
        if start_id and clip_id == start_id:
            break

        parent = str(current.get("parent_clip_id") or "").strip()
        if not parent or parent in INITIAL_MARKERS:
            break
        current = find_clip(clips, parent)
        if current is None:
            warnings.append("「%s」的父镜头「%s」不在库里（可能已删除），血缘在此断开" % (clip_id, parent))
            break
        if len(chain) >= MAX_CHAIN:
            warnings.append("血缘长度超过 %d 段，已在此停止回溯" % MAX_CHAIN)
            break

    chain.reverse()
    return chain, warnings


def pick_variant(meta: Dict[str, Any], policy: str) -> Tuple[str, str, Dict[str, Any]]:
    """Chooses which archived video to use for one card.

    Returns (variant label, video filename, that variant's meta). Single-variant
    cards have no variant dict; their label is "" and the policy does not apply.
    """
    variants = meta.get("variants") or {}
    if isinstance(variants, dict) and variants:
        if policy == VARIANT_ONLY_FIRST:
            order = ["一采"]
        elif policy == VARIANT_ONLY_UP:
            order = ["二采"]
        else:
            order = ["二采", "一采"]
        for name in order:
            variant = variants.get(name)
            if isinstance(variant, dict) and variant.get("has_video") and variant.get("video_file"):
                return name, str(variant["video_file"]), variant
        return "", "", {}

    if meta.get("has_video") and meta.get("video_file"):
        return "", str(meta["video_file"]), meta
    return "", "", {}


def _parse_rate(value: Any) -> float:
    """Converts an ffprobe rate such as 30000/1001 into frames per second."""
    text = str(value or "").strip()
    if not text or text in ("0/0", "N/A"):
        return 0.0
    num, _, den = text.partition("/")
    try:
        if den:
            divisor = float(den)
            return float(num) / divisor if divisor else 0.0
        return float(num)
    except ValueError:
        return 0.0


def parse_probe_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts the fields the join decision depends on out of an ffprobe JSON dump.

    Frame count prefers the container's ``nb_frames``; when the muxer did not
    record it, duration x fps is used and flagged as an estimate.
    """
    out: Dict[str, Any] = {
        "width": 0, "height": 0, "fps": 0.0, "frames": 0, "duration": 0.0,
        "frames_estimated": False, "has_audio": False, "sample_rate": 0,
        "vcodec": "", "acodec": "",
    }
    format_duration = _parse_rate((payload.get("format") or {}).get("duration"))

    for stream in payload.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and not out["vcodec"]:
            out["width"] = int(stream.get("width") or 0)
            out["height"] = int(stream.get("height") or 0)
            out["fps"] = _parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
            out["duration"] = _parse_rate(stream.get("duration")) or format_duration
            out["vcodec"] = str(stream.get("codec_name") or "")
            nb = stream.get("nb_frames")
            try:
                nb_frames = int(nb) if nb not in (None, "N/A", "") else 0
            except (TypeError, ValueError):
                nb_frames = 0
            if nb_frames > 0:
                out["frames"] = nb_frames
            elif out["duration"] > 0 and out["fps"] > 0:
                out["frames"] = int(round(out["duration"] * out["fps"]))
                out["frames_estimated"] = True
        elif kind == "audio" and not out["has_audio"]:
            out["has_audio"] = True
            out["acodec"] = str(stream.get("codec_name") or "")
            try:
                out["sample_rate"] = int(stream.get("sample_rate") or 0)
            except (TypeError, ValueError):
                out["sample_rate"] = 0
            out["duration"] = max(out["duration"], _parse_rate(stream.get("duration")))

    if out["duration"] <= 0:
        out["duration"] = format_duration
    return out


def probe_video_streams(path: str) -> Optional[Dict[str, Any]]:
    """Measures a video file's real stream parameters. None when ffprobe cannot read it."""
    ffprobe_bin = _find_ffprobe()
    if not ffprobe_bin or not os.path.isfile(path):
        return None
    try:
        proc = subprocess.run(
            [ffprobe_bin, "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", path],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        return parse_probe_json(json.loads(proc.stdout or "{}"))
    except Exception as exc:
        logger.debug("[Long Builder] ffprobe failed for '%s': %s", path, exc)
        return None


def classify_join(samples: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Decides whether every segment can be stream-copied into one file.

    The concat demuxer with ``-c copy`` only produces a playable film when the
    segments share width, height, frame rate, and an audio stream of the same
    sample rate. Anything else has to be re-encoded, and pretending otherwise is
    how a silent or stuttering long video slips out.
    """
    reasons: List[str] = []
    if len(samples) < 2:
        return True, reasons
    base = samples[0]
    for index, sample in enumerate(samples[1:], start=2):
        label = sample.get("label") or ("第 %d 段" % index)
        if (sample.get("width"), sample.get("height")) != (base.get("width"), base.get("height")):
            reasons.append("%s 分辨率 %sx%s 与首段 %sx%s 不同" % (
                label, sample.get("width"), sample.get("height"),
                base.get("width"), base.get("height")))
        if abs(float(sample.get("fps") or 0) - float(base.get("fps") or 0)) > 0.01:
            reasons.append("%s 帧率 %.3f 与首段 %.3f 不同" % (
                label, float(sample.get("fps") or 0), float(base.get("fps") or 0)))
        if bool(sample.get("has_audio")) != bool(base.get("has_audio")):
            reasons.append("%s 的音轨有无与首段不一致" % label)
        elif sample.get("has_audio") and sample.get("sample_rate") and base.get("sample_rate") \
                and sample["sample_rate"] != base["sample_rate"]:
            reasons.append("%s 音频采样率 %s 与首段 %s 不同" % (
                label, sample["sample_rate"], base["sample_rate"]))
    return not reasons, reasons


def seam_warnings(segments: List[Dict[str, Any]]) -> List[str]:
    """Flags segments whose archived video still contains the overlap frames.

    Continuation re-generates the pinned frames at the head of every segment, and
    the Trim node is what removes them. When a card was saved with the untrimmed
    frames, the long film repeats a beat at that join. The latent frame count and
    the measured video frame count are equal exactly in that case, which is the
    cheapest reliable signal - no frame decoding needed.
    """
    warnings: List[str] = []
    for index, segment in enumerate(segments, start=1):
        if index == 1:
            continue  # the first shot has no overlap by definition
        latent = int(segment.get("latent_frames") or 0)
        video = int(segment.get("frames") or 0)
        if latent <= 0 or video <= 0 or segment.get("frames_estimated"):
            continue
        if video >= latent:
            warnings.append(
                "第 %d 段「%s」的视频有 %d 帧，没有少于 latent 的 %d 帧：接缝处的重复帧没有被裁掉，"
                "长片在这里会重复一小段画面。把 Trim 之后的 images/audio 接回 Saver 重新归档这一段，再拼一次。"
                % (index, segment.get("label") or "?", video, latent))
    return warnings


def concat_list_text(paths: List[str]) -> str:
    """Builds an ffmpeg concat list. Paths are forward-slashed and quote-escaped."""
    lines = ["ffconcat version 1.0"]
    for path in paths:
        escaped = path.replace("\\", "/").replace("'", "'\\''")
        lines.append("file '%s'" % escaped)
    return "\n".join(lines) + "\n"


def concat_videos(paths: List[str], output_path: str, mode: str,
                  fps: float = 24.0, has_audio: bool = False) -> Tuple[str, str]:
    """Runs ffmpeg over the concat list. Returns ("copy"|"reencode", stderr tail)."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise ValueError("h3_clipstream: 找不到 ffmpeg，无法拼接。请确认 ffmpeg 在 PATH 中（归档卡片视频时也用得到它）。")

    list_path = os.path.join(os.path.dirname(os.path.abspath(output_path)),
                             "_concat_%s.txt" % datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    with open(list_path, "w", encoding="utf-8") as stream:
        stream.write(concat_list_text(paths))

    try:
        base = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_path]
        if mode == JOIN_COPY:
            cmd = base + ["-c", "copy", "-movflags", "+faststart", output_path]
        else:
            cmd = base + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart"]
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            cmd.append(output_path)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            tail = (proc.stderr or "").strip().splitlines()[-12:]
            raise ValueError("h3_clipstream: ffmpeg 拼接失败（退出码 %s）：%s"
                             % (proc.returncode, " | ".join(tail) or "ffmpeg 没有输出错误信息"))
        return ("copy" if mode == JOIN_COPY else "reencode"), (proc.stderr or "")
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass


def build_long_video(project_name: str,
                     end_clip_id: str = "latest",
                     start_clip_id: str = "",
                     clip_sequence: str = "",
                     variant_policy: str = VARIANT_PREFER_UP,
                     join_mode: str = JOIN_AUTO,
                     fps: float = 24.0,
                     skip_missing: bool = False,
                     output_name: str = "") -> Dict[str, Any]:
    """Joins the archived videos of one project's shot chain into a single MP4.

    Returns a dict with path, total_frames, duration_seconds, segments, warnings,
    join_method and a human-readable report.
    """
    p_name = (project_name or "Default_Project").strip()
    clips = list_bin_clips(p_name)
    chain, warnings = resolve_shot_order(clips, end_clip_id, start_clip_id, clip_sequence)
    if not chain:
        raise ValueError("h3_clipstream: 项目「%s」里没有可拼接的镜头。%s" % (p_name, " ".join(warnings)))

    project_dir = get_project_dir(p_name)
    segments: List[Dict[str, Any]] = []
    missing: List[str] = []
    for clip_id in chain:
        meta = next((c for c in clips if c.get("clip_id") == clip_id), {})
        label = "%s（%s）" % (meta.get("shot_tag") or clip_id, clip_id)
        variant, video_file, variant_meta = pick_variant(meta, variant_policy)
        video_path = os.path.join(project_dir, clip_id, video_file) if video_file else ""
        if not video_path or not os.path.isfile(video_path):
            missing.append("%s [%s]" % (label, variant) if variant else label)
            continue
        probe = probe_video_streams(video_path)
        if probe is None:
            raise ValueError("h3_clipstream: 读不到「%s」的视频参数（%s）。请确认 ffprobe 可用，"
                             "且该文件没有被其他程序占用。" % (label, video_path))
        segments.append({
            "clip_id": clip_id,
            "label": label,
            "variant": variant,
            "video_path": video_path,
            "latent_frames": int(variant_meta.get("frames") or meta.get("frames") or 0),
            **probe,
        })

    if missing:
        message = "以下镜头没有归档视频：" + "、".join(missing)
        if not skip_missing:
            raise ValueError("h3_clipstream: " + message +
                             "。要么在 Saver 里打开 save_video 重新归档这些段，要么打开本节点的 skip_missing。")
        warnings.append(message + "（skip_missing 已开启，这些段被跳过）")

    if not segments:
        raise ValueError("h3_clipstream: 项目「%s」的镜头链里没有一段带归档视频。" % p_name)

    warnings.extend(seam_warnings(segments))

    can_copy, mismatch = classify_join(segments)
    if join_mode == JOIN_COPY and not can_copy:
        raise ValueError("h3_clipstream: 各段参数不一致，无损直拷会出坏片：" + "；".join(mismatch) +
                         "。请改用 auto 或 reencode。")
    if not can_copy:
        warnings.append("各段参数不一致，已改用重编码统一：" + "；".join(mismatch))

    mode = JOIN_COPY if can_copy else JOIN_REENCODE
    if join_mode == JOIN_REENCODE:
        mode = JOIN_REENCODE

    slug = re.sub(r"[^0-9A-Za-z_-]+", "_", sanitize_project_name(p_name)) or "project"
    name = (output_name or "").strip().strip('"').strip("'")
    if not name:
        name = "%s_%02dshots_%s.mp4" % (slug, len(segments), datetime.now().strftime("%Y%m%d_%H%M%S"))
    if not name.lower().endswith(".mp4"):
        name += ".mp4"
    out_path = os.path.join(get_long_dir(p_name), name)

    join_method, _stderr = concat_videos(
        [segment["video_path"] for segment in segments], out_path, mode,
        fps=fps, has_audio=any(segment.get("has_audio") for segment in segments))

    total_frames = sum(int(segment.get("frames") or 0) for segment in segments)
    duration = sum(float(segment.get("duration") or 0.0) for segment in segments)
    final_probe = probe_video_streams(out_path)
    if final_probe and final_probe.get("frames"):
        total_frames = int(final_probe["frames"])
        duration = float(final_probe.get("duration") or duration)

    report = format_report(p_name, segments, out_path, join_method, total_frames, duration, warnings)
    logger.info("[Long Builder] '%s' -> '%s' (%d frames, %.2fs, %s)",
                p_name, out_path, total_frames, duration, join_method)
    return {
        "path": out_path,
        "total_frames": total_frames,
        "duration_seconds": round(duration, 3),
        "segments": segments,
        "warnings": warnings,
        "join_method": join_method,
        "report": report,
    }


def format_report(project_name: str, segments: List[Dict[str, Any]], output_path: str,
                  join_method: str, total_frames: int, duration: float,
                  warnings: List[str]) -> str:
    """Renders the per-segment audit that the node returns as its report output."""
    lines = ["长视频拼接报告 · 项目「%s」" % project_name,
             "镜头顺序（%d 段）：" % len(segments)]
    for index, segment in enumerate(segments, start=1):
        variant = " [%s]" % segment["variant"] if segment.get("variant") else ""
        audio = "有声" if segment.get("has_audio") else "无声"
        lines.append("  %d. %s%s  %sx%s %.3ffps %d帧 %.2fs %s" % (
            index, segment.get("label") or "?", variant,
            segment.get("width"), segment.get("height"), float(segment.get("fps") or 0),
            int(segment.get("frames") or 0), float(segment.get("duration") or 0), audio))
    lines.append("拼接方式：%s" % ("无损直拷（未重编码）" if join_method == "copy" else "重编码统一"))
    lines.append("输出：%s  共 %d 帧 / %.2fs" % (output_path, total_frames, duration))
    if warnings:
        lines.append("注意：")
        for warning in warnings:
            lines.append("  - " + warning)
    return "\n".join(lines)
