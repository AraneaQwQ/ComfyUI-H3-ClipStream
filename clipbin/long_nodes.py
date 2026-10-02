"""Clip Bin long-video builder: shot order in, one MP4 out.

The bin already holds every generated segment's video; the missing step is the
stitching. This node reads the archived videos back in shot order and writes one
long film, so the user no longer has to line the segments up by hand.

It is a read-side node like the Pickers: it never writes into a card, never
touches a latent, and never re-encodes unless the segments cannot be joined as
they are.
"""

from comfy_api.latest import io

import logging

from .long_builder import (
    build_long_video,
    JOIN_AUTO,
    JOIN_MODES,
    VARIANT_PREFER_UP,
    VARIANT_POLICIES,
)

logger = logging.getLogger("minimax_clip_bin_long")


class MiniMaxClipBinLongBuilderNode(io.ComfyNode):
    """Concatenates the archived videos of a project's shot chain into one long video.

    Order comes from the lineage the Pickers already recorded (``parent_clip_id``);
    a hand-written sequence overrides it for branched projects. Every segment is
    measured with ffprobe before anything is written, so mismatched resolution,
    frame rate or audio parameters are reported instead of producing a broken film.
    """

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id='MiniMaxClipBinLongBuilder',
            display_name='MiniMax H3 Clip Long Builder (长视频拼接)',
            category='MiniMaxH3/ClipStream',
            description='按镜头顺序读取 Clip Bin 卡片里已归档的 MP4，检查参数一致性后用 ffmpeg 拼接成一个长视频。',
            is_output_node=True,
            inputs=[
                io.String.Input('project_name', default='Default_Project', tooltip='【项目库名称】与 Picker 用的是同一个项目名，节点从这个库里找镜头'),
                io.String.Input('end_clip_id', default='latest', tooltip="【终点镜头】\n• 填 'latest'（默认）：以库里最新的一段为终点\n• 填 clip_id 或 shot 标签的一部分：从该镜头往回回溯血缘\n拼接方向始终是从最早的一段到这里的终点。"),
                io.String.Input('start_clip_id', optional=True, default='', tooltip='【起点镜头】可选。回溯到这个镜头就停；留空则一直回溯到没有父镜头的第一段。只想拼最后几段时填它。'),
                io.String.Input('clip_sequence', optional=True, default='', tooltip="【手动镜头顺序】可选，用逗号或换行分隔的 clip_id / shot 标签，按书写顺序直接拼接，完全跳过血缘回溯。项目里分了支、想指定走哪一条线时用它。"),
                io.Combo.Input('variant_policy', options=list(VARIANT_POLICIES), default=VARIANT_PREFER_UP, tooltip='【取哪个变体的视频】\n• 优先二采：卡片里有二采视频就用二采，没有则退回一采（推荐）。\n• 仅一采 / 仅二采：只用指定变体；该段没有这个变体时按下面的缺段策略处理。'),
                io.Combo.Input('join_mode', options=list(JOIN_MODES), default=JOIN_AUTO, tooltip='【拼接方式】\n• auto：分辨率/帧率/音频参数一致时无损直拷（最快、不损画质），不一致时自动重编码统一。\n• copy：只允许无损直拷，参数不一致直接报错，适合确认过参数一致的项目。\n• reencode：一律重编码，用来把不同分辨率的历史片段强行接在一起。'),
                io.Float.Input('fps', optional=True, default=24.0, min=1.0, max=240.0, step=0.001, tooltip='【重编码帧率】只在需要重编码时使用，应与生成时的帧率一致（默认 24）。'),
                io.Boolean.Input('skip_missing', optional=True, default=False, tooltip='【缺段是否跳过】某段没有归档视频时：False（默认）直接报错并列出缺哪些镜头；True 则跳过这些段继续拼，报告里会写明。'),
                io.String.Input('output_name', optional=True, default='', tooltip='【输出文件名】可选，留空则用 项目名_段数_时间戳.mp4。输出在 output/h3_long/<项目>/ 下，不会进入卡片库。'),
            ],
            outputs=[
                io.String.Output(display_name='filename', tooltip='拼好的长视频绝对路径，可直接接 VHS_VideoCombine / SaveVideo 或本地播放'),
                io.Int.Output(display_name='total_frames', tooltip='长视频实测总帧数'),
                io.Float.Output(display_name='duration_seconds', tooltip='长视频实测时长（秒）'),
                io.String.Output(display_name='report', tooltip='逐段清单 + 拼接方式 + 接缝与参数警告。接缝处的重复帧只在这里说明，卡片上不标注。'),
            ],
        )

    @classmethod
    def execute(cls,
               project_name: str = "Default_Project",
               end_clip_id: str = "latest",
               start_clip_id: str = "",
               clip_sequence: str = "",
               variant_policy: str = VARIANT_PREFER_UP,
               join_mode: str = JOIN_AUTO,
               fps: float = 24.0,
               skip_missing: bool = False,
               output_name: str = "",
               **kwargs) -> io.NodeOutput:
        result = build_long_video(
            project_name=project_name,
            end_clip_id=end_clip_id,
            start_clip_id=start_clip_id,
            clip_sequence=clip_sequence,
            variant_policy=variant_policy,
            join_mode=join_mode,
            fps=fps,
            skip_missing=skip_missing,
            output_name=output_name,
        )
        for warning in result["warnings"]:
            logger.warning("[Long Builder] %s", warning)
        return io.NodeOutput(result["path"], result["total_frames"],
                             result["duration_seconds"], result["report"])


NODE_LIST = [MiniMaxClipBinLongBuilderNode]
