"""AI analysis interface and local suggestion provider.

The local provider is deterministic and offline. It keeps the AI advice layer
usable before binding a real model provider.
"""

from __future__ import absolute_import

from asset_forge.shared.constants import CHECK_STATUS_ERROR, CHECK_STATUS_WARNING
from asset_forge.shared.rules_schema import get_default_rules


class AiAnalysisInput(object):
    """Serializable input object for AI analysis providers."""

    def __init__(self, scan_result, validation_result, project_rules=None, target_platform=None):
        self.scan_result = scan_result or {}
        self.validation_result = validation_result or {}
        self.project_rules = project_rules or get_default_rules()
        self.target_platform = target_platform or self.validation_result.get("target_platform", "")

    def to_dict(self):
        return {
            "asset_name": self.scan_result.get("asset_name", ""),
            "asset_type": self.validation_result.get("asset_type", ""),
            "target_platform": self.target_platform,
            "score": self.validation_result.get("score", 0),
            "status": self.validation_result.get("status", ""),
            "can_export": self.validation_result.get("can_export", False),
            "checks": self.validation_result.get("checks", []),
            "scan": self.scan_result,
            "project_rules": self.project_rules,
        }


class AiAnalysisClient(object):
    """Provider interface for analysis suggestions."""

    provider_name = "base"

    def analyze(self, analysis_input):
        raise NotImplementedError


class LocalChineseSuggestionClient(AiAnalysisClient):
    """Offline Chinese suggestion provider for v0.1."""

    provider_name = "local_zh"

    def analyze(self, analysis_input):
        data = analysis_input.to_dict()
        checks = data.get("checks", [])
        failed_checks = [item for item in checks if item.get("status") in (CHECK_STATUS_ERROR, CHECK_STATUS_WARNING)]

        if not failed_checks:
            return self._pass_message(data)

        lines = [
            "资产 {0} 当前评分 {1}，状态为 {2}。".format(
                data.get("asset_name", ""),
                data.get("score", 0),
                data.get("status", ""),
            ),
            "以下建议只作为解释和修复参考，不参与通过 / 失败判定。",
            "",
        ]

        for item in failed_checks:
            lines.append(self._suggestion_for_check(item, data))

        if not data.get("can_export", False):
            lines.append("")
            lines.append("当前存在阻塞错误，建议修复 error 项后再导出。")
        else:
            lines.append("")
            lines.append("当前问题为 warning 级别，可以导出，但建议在入库前完成优化。")

        return "\n".join([line for line in lines if line is not None])

    def _pass_message(self, data):
        return "\n".join(
            [
                "资产 {0} 当前评分 {1}，检查结果为通过。".format(
                    data.get("asset_name", ""),
                    data.get("score", 0),
                ),
                "可以进入 FBX 导出和 Unreal 导入流程。",
                "AI 建议层只做解释，不改变检查结果。",
            ]
        )

    def _suggestion_for_check(self, item, data):
        check_id = item.get("id")
        label = item.get("label", check_id)
        message = item.get("message", "")

        handlers = {
            "name_prefix": "将资产根节点命名为 SM_ 开头，例如 SM_Crate_01，以匹配 Unreal Static Mesh 命名规范。",
            "mesh_exists": "确认选择的是资产根节点，并且其层级下存在 polygon mesh。",
            "empty_mesh": "删除空 mesh，或检查导出根节点下是否包含无面数的残留 shape。",
            "frozen_transform": "在 Maya 中执行 Freeze Transformations，确保 Translate/Rotate 归零，Scale 为 1。",
            "illegal_scale": "检查是否存在 0 或负数缩放；这类缩放进入 UE 后容易造成法线、碰撞或包围盒异常。",
            "triangle_budget": "根据目标平台 {0} 优化面数，优先处理不可见面、过密倒角和可用贴图替代的细节。".format(
                data.get("target_platform", "")
            ),
            "material_slots": "合并材质或整理 ID，减少 draw call；移动端和高端移动端尤其应控制材质槽数量。",
            "uv0": "补充基础 UV0，确保贴图采样和材质表现稳定。",
            "lightmap_uv": "补充第二套不重叠 UV，或确认 UE 导入阶段允许生成 Lightmap UV。",
            "hidden_objects": "清理隐藏对象，避免误导出或造成 manifest 与实际 FBX 内容不一致。",
            "history_nodes": "执行 Delete History，清理建模历史节点，降低导出不确定性。",
        }

        suggestion = handlers.get(check_id, "检查该项对应资产状态，并按项目规范修复。")
        return "- [{0}] {1}：{2} 建议：{3}".format(item.get("status", ""), label, message, suggestion)


def build_analysis_input(scan_result, validation_result, project_rules=None, target_platform=None):
    return AiAnalysisInput(scan_result, validation_result, project_rules, target_platform)


def analyze_validation(scan_result, validation_result, project_rules=None, client=None):
    analysis_input = build_analysis_input(
        scan_result,
        validation_result,
        project_rules,
        validation_result.get("target_platform", ""),
    )
    active_client = client or LocalChineseSuggestionClient()
    return active_client.analyze(analysis_input)
