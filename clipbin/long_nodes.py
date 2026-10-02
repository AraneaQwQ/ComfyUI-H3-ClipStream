"""Clip Bin long-video builder: pick the shots in the panel, get one film back.

The bin already holds every generated segment's video; the missing step is the
stitching. This node reads the archived videos back in shot-number order and
writes one long film, so the user no longer has to line the segments up by hand.

It is a read-side node like the Pickers: it never writes into a card, never
touches a latent, and never re-encodes unless the segments cannot be joined as
they are. The node itself exposes one VIDEO output, which the front-end panel and
the inline preview both use; the per-segment audit goes to the ComfyUI log.
"""

from comfy_api.latest import io, InputImpl, ui

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
    """Concatenates the archived videos of a project into one long video.

    Order comes from the shot number on each card (Shot 1, Shot 2, ...), which is
    the order the film was generated in; the panel lists the cards and one click
    leaves a take out. Every segment is measured with ffprobe before anything is
    written, so mismatched resolution, frame rate or audio parameters are reported
    instead of producing a broken film.
    """

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id='MiniMaxClipBinLongBuilder',
            display_name='MiniMax H3 Clip Long Builder (长视频拼接)',
            category='MiniMaxH3/ClipStream',
            description='按镜头序号读取 Clip Bin 卡片里已归档的 MP4，检查参数一致性后用 ffmpeg 拼接成一个长视频，节点上直接预览。',
            is_output_node=True,
            inputs=[
                io.String.Input('project_name', advanced=True, default='Default_Project',
                                tooltip='【项目库名称】面板上的项目下拉框会写入这里。手动填写也可以，填完点面板的「刷新」再选卡片。'),
                io.String.Input('exclude_clips', optional=True, advanced=True, default='',
                                tooltip='【排除的镜头】面板上点掉的卡片会写在这里（clip_id 用逗号分隔）。这些卡片不参与拼接；手动填镜头标签的一部分也可以。'),
                io.Combo.Input('variant_policy', options=list(VARIANT_POLICIES), advanced=True, default=VARIANT_PREFER_UP,
                               tooltip='【取哪个变体的视频】\n• 优先二采：卡片里有二采视频就用二采，没有则退回一采（推荐）。\n• 仅一采 / 仅二采：只用指定变体；该段没有这个变体时会被跳过并在日志里说明。'),
                io.Combo.Input('join_mode', options=list(JOIN_MODES), advanced=True, default=JOIN_AUTO,
                               tooltip='【拼接方式】\n• auto：分辨率/帧率/音频参数一致时无损直拷（最快、不损画质），不一致时自动重编码统一。\n• copy：只允许无损直拷，参数不一致直接报错，适合确认过参数一致的项目。\n• reencode：一律重编码，用来把不同分辨率的历史片段强行接在一起。'),
                io.Float.Input('fps', optional=True, advanced=True, default=24.0, min=1.0, max=240.0, step=0.001,
                               tooltip='【重编码帧率】只在需要重编码时使用，应与生成时的帧率一致（默认 24）。'),
                io.String.Input('output_name', optional=True, advanced=True, default='',
                                tooltip='【输出文件名】可选，留空则用 项目名_段数_时间戳.mp4。输出在 output/h3_long/<项目>/ 下，不会进入卡片库。'),
            ],
            outputs=[
                io.Video.Output('video', tooltip='拼好的长视频：可直接接 SaveVideo / VHS_VideoCombine，节点自身也会内联预览。'),
            ],
        )

    @classmethod
    def execute(cls,
               project_name: str = "Default_Project",
               exclude_clips: str = "",
               variant_policy: str = VARIANT_PREFER_UP,
               join_mode: str = JOIN_AUTO,
               fps: float = 24.0,
               output_name: str = "",
               **kwargs) -> io.NodeOutput:
        result = build_long_video(
            project_name=project_name,
            exclude_clips=exclude_clips,
            variant_policy=variant_policy,
            join_mode=join_mode,
            fps=fps,
            output_name=output_name,
        )
        for warning in result["warnings"]:
            logger.warning("[Long Builder] %s", warning)
        # The sockets were dropped on purpose, so the audit trail lives in the log.
        logger.info("[Long Builder]\n%s", result["report"])
        return io.NodeOutput(
            InputImpl.VideoFromFile(result["path"]),
            ui=ui.PreviewVideo([ui.SavedResult(result["filename"], result["subfolder"],
                                              io.FolderType.output)]),
        )


NODE_LIST = [MiniMaxClipBinLongBuilderNode]
