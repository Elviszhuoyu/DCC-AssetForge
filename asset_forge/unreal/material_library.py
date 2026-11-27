"""DCC AssetForge material library rules for Unreal."""

from __future__ import absolute_import


SURFACE_PBR_FAMILY = "MM_Surface_PBR"
from asset_forge.shared.material_profile_schema import PROPS_PAINTER_OPAQUE_MASTER


AF_PROPS_MASTER = "/AssetForge/Materials/M_AF_Props_Master"
AF_HARDSURFACE_MASTER = AF_PROPS_MASTER
AF_ENVIRONMENT_MASTER = "/AssetForge/Materials/M_AF_Environment_Master"
AF_CHARACTER_MASTER = "/AssetForge/Materials/M_AF_Character_Master"
AF_CHARACTER_BASIC = AF_CHARACTER_MASTER
AF_EMISSIVE_SURFACE = AF_PROPS_MASTER

PARAMETER_API_MAPPING = {
    "BaseColor": "Base Color",
    "Normal": "Normal Map",
    "ARM": "Pack Map",
    "ORM": "Pack Map",
    "OpacityMask": "Opacity Map",
    "Opacity": "Opacity Map",
    "MaskContrast": "Mask Contrast",
    "Emissive": "Emissive Map",
    "ImperfectionMask": "Imperfection Mask",
    "Height": "Height Map",
    "UVTiling": "UV Tile",
    "WorldAlignedScale": "World Aligned Scale",
    "ProjectionBlendSharpness": "Projection Blend Sharpness",
    "HeightScale": "Height Scale",
    "POMMinSteps": "POM Min Steps",
    "POMMaxSteps": "POM Max Steps",
    "POMTemporalAAStepMultiplier": "POM Temporal AA Step Multiplier",
    "DecalAlphaSharpness": "Decal Alpha Sharpness",
    "RefractionDepthBias": "Refraction Depth Bias",
    "BaseColorIntensity": "Base Color Intensity",
    "BaseColorTint": "Tint",
    "NormalStrength": "Normal Intensity",
    "RoughnessIntensity": "Roughness Intensity",
    "RoughnessMin": "Roughness Min",
    "RoughnessMax": "Roughness Max",
    "MetallicIntensity": "Metallic Value",
    "AOIntensity": "AO Value",
    "Specular": "Specular Value",
    "ImperfectionIntensity": "Imperfection Intensity",
    "EdgeWearIntensity": "Edge Wear Intensity",
    "OpacityClipValue": "Opacity Clip Value",
    "OpacityIntensity": "Opacity Intensity",
    "EmissiveTint": "Emissive Tint",
    "EmissiveIntensity": "Emissive Intensity",
    "SubsurfaceTint": "Subsurface Tint",
    "SubsurfaceIntensity": "Subsurface Intensity",
    "SkinRoughnessBias": "Skin Roughness Bias",
    "MicroNormalStrength": "Micro Normal Strength",
    "MacroVariationScale": "Macro Variation Scale",
    "MacroVariationIntensity": "Macro Variation Intensity",
    "UseOpacityMask": "Use Opacity Mask",
    "UseSeparateOpacityMask": "Use Separate Opacity Mask",
    "UseEmissive": "Use Emissive",
    "UseImperfections": "Use Imperfections",
    "UseWear": "Use Wear",
    "UseWorldAligned": "Use World Aligned",
    "UseTriplanar": "Use Triplanar",
    "UseVirtualTextures": "Use Virtual Textures",
    "UseSubsurface": "Use Subsurface",
}

PARAMETER_DESCRIPTIONS = {
    "BaseColor": "基础色贴图。RGB 控制材质颜色；A 通道默认作为 Masked 材质的镂空遮罩来源。",
    "Normal": "法线贴图。保持 Normal sampler，避免 UE 将切线空间法线当作普通颜色采样。",
    "ARM": "ARM 打包贴图。R=AO 环境遮蔽，G=Roughness 粗糙度，B=Metallic 金属度；必须使用非颜色/Masks 采样。",
    "ORM": "ORM 打包贴图。R=Occlusion，G=Roughness，B=Metallic；语义等同 ARM，仅命名来自不同 DCC/烘焙工具。",
    "OpacityMask": "独立透明遮罩贴图。只有资产确实提供单独 Mask 时使用；普通道具优先使用 BaseColor.A 节省采样器。",
    "Opacity": "半透明 Opacity 贴图。用于 Translucent 材质，不等同于 Masked 的硬切遮罩。",
    "Emissive": "自发光贴图。实例中开启 UseEmissive 后才会参与 Emissive Color 输出。",
    "ImperfectionMask": "瑕疵/污渍/磨损遮罩。用于预览和材质实例调节脏污强度，不应作为颜色贴图采样。",
    "Height": "高度贴图。预留给 POM/位移类效果；默认母材质不强制启用昂贵分支。",
    "UVTiling": "统一 UV 平铺倍数。1 表示使用模型原始 UV；增大数值会让所有贴图重复更密。",
    "BaseColorTint": "基础色染色。与 BaseColor 相乘，用于快速统一色相或做轻量变体。",
    "BaseColorIntensity": "基础色亮度倍率。建议保持在 0.5-2 范围，避免破坏 PBR 能量关系。",
    "NormalStrength": "法线强度。1 为原始法线；0 接近平面；大于 1 会增强细节但可能产生噪点。",
    "AOIntensity": "AO 强度。作用于 ARM.R；1 为贴图原值，0 会关闭贴图 AO 影响。",
    "RoughnessIntensity": "粗糙度强度。作用于 ARM.G；提高会更哑光，降低会更光滑。",
    "MetallicIntensity": "金属度强度。作用于 ARM.B；金属道具通常为 1，非金属保持 0。",
    "Specular": "非金属高光强度。常用 0.3-0.6；除非有明确材质依据，不建议极端调整。",
    "ImperfectionIntensity": "瑕疵强度。0 关闭脏污/磨损预览；提高后 ImperfectionMask 会压暗或强化表面变化。",
    "EmissiveTint": "自发光颜色染色。与 Emissive 贴图相乘，用于统一灯带或屏幕色相。",
    "EmissiveIntensity": "自发光亮度倍率。UseEmissive 开启后生效；数值越高 Bloom 越明显。",
    "MaskContrast": "遮罩对比/强度。作用于 BaseColor.A 或 OpacityMask.R；提高会让镂空边界更硬。",
    "OpacityClipValue": "Masked 剪裁阈值。高于该值的像素保留，低于该值剔除；常用 0.2-0.5。",
    "OpacityIntensity": "半透明强度倍率。用于 Opacity 贴图，不控制 Masked 镂空。",
    "UseEmissive": "自发光开关。0 输出黑色不发光；1 使用 Emissive 贴图、染色和强度参数。",
    "UseOpacityMask": "镂空遮罩总开关。0 完全不镂空；1 启用 BaseColor.A 或独立 OpacityMask 分支。",
    "UseSeparateOpacityMask": "独立遮罩开关。0 使用 BaseColor.A；1 使用 OpacityMask.R，只有存在单独遮罩贴图时开启。",
    "UseSubsurface": "次表面开关。角色/皮肤材质使用；道具和硬表面默认不要开启。",
    "SubsurfaceTint": "次表面颜色。用于皮肤或半透材质的透光色调。",
    "SubsurfaceIntensity": "次表面强度。0 关闭透光感；提高后皮肤/蜡质感更明显。",
    "UseOpacityMaskOffValue": "遮罩关闭时的安全值。固定输出 1，让材质保持完全不镂空。",
    "UseEmissiveOffValue": "自发光关闭时的安全值。固定输出 0，避免实例未开启时意外发光。",
}

PARAMETER_GROUPS = {
    "UseVirtualTextures": "01 UV 输入 / UV",
    "UseWorldAligned": "01 UV 输入 / UV",
    "UseTriplanar": "01 UV 输入 / UV",
    "WorldAlignedScale": "01 UV 输入 / UV",
    "ProjectionBlendSharpness": "01 UV 输入 / UV",
    "BaseColor": "02 基础色 / BaseColor",
    "BaseColorTint": "02 基础色 / BaseColor",
    "BaseColorIntensity": "02 基础色 / BaseColor",
    "Normal": "03 法线 / Normal",
    "NormalStrength": "03 法线 / Normal",
    "ARM": "04 ARM 打包 / PBR",
    "ORM": "04 ARM 打包 / PBR",
    "AOIntensity": "04 ARM 打包 / PBR",
    "RoughnessIntensity": "04 ARM 打包 / PBR",
    "RoughnessMin": "04 ARM 打包 / PBR",
    "RoughnessMax": "04 ARM 打包 / PBR",
    "MetallicIntensity": "04 ARM 打包 / PBR",
    "Specular": "04 ARM 打包 / PBR",
    "ImperfectionMask": "05 瑕疵 / Imperfection",
    "ImperfectionIntensity": "05 瑕疵 / Imperfection",
    "UseImperfections": "05 瑕疵 / Imperfection",
    "UseWear": "05 瑕疵 / Imperfection",
    "EdgeWearIntensity": "05 瑕疵 / Imperfection",
    "Emissive": "06 自发光 / Emissive",
    "EmissiveTint": "06 自发光 / Emissive",
    "EmissiveIntensity": "06 自发光 / Emissive",
    "UseEmissive": "06 自发光 / Emissive",
    "UseEmissiveOffValue": "06 自发光 / Emissive",
    "OpacityMask": "07 镂空 / Opacity Mask",
    "Opacity": "07 镂空 / Opacity Mask",
    "MaskContrast": "07 镂空 / Opacity Mask",
    "OpacityClipValue": "07 镂空 / Opacity Mask",
    "OpacityIntensity": "07 镂空 / Opacity Mask",
    "UseOpacityMask": "07 镂空 / Opacity Mask",
    "UseSeparateOpacityMask": "07 镂空 / Opacity Mask",
    "UseOpacityMaskOffValue": "07 镂空 / Opacity Mask",
    "Height": "08 高度 / Height",
    "HeightScale": "08 高度 / Height",
    "POMMinSteps": "08 高度 / Height",
    "POMMaxSteps": "08 高度 / Height",
    "POMTemporalAAStepMultiplier": "08 高度 / Height",
    "SubsurfaceTint": "09 次表面 / Subsurface",
    "SubsurfaceIntensity": "09 次表面 / Subsurface",
    "SkinRoughnessBias": "09 次表面 / Subsurface",
    "MicroNormalStrength": "09 次表面 / Subsurface",
    "MacroVariationScale": "09 次表面 / Subsurface",
    "MacroVariationIntensity": "09 次表面 / Subsurface",
    "UseSubsurface": "09 次表面 / Subsurface",
    "UVTiling": "01 UV 输入 / UV",
}

PARAMETER_SORT_PRIORITIES = {
    "UVTiling": 10,
    "BaseColor": 100,
    "BaseColorTint": 110,
    "BaseColorIntensity": 120,
    "Normal": 200,
    "NormalStrength": 210,
    "ARM": 300,
    "ORM": 300,
    "AOIntensity": 310,
    "RoughnessIntensity": 320,
    "RoughnessMin": 321,
    "RoughnessMax": 322,
    "MetallicIntensity": 330,
    "Specular": 340,
    "ImperfectionMask": 400,
    "ImperfectionIntensity": 410,
    "EdgeWearIntensity": 420,
    "Emissive": 500,
    "EmissiveTint": 510,
    "EmissiveIntensity": 520,
    "UseEmissive": 530,
    "UseEmissiveOffValue": 540,
    "OpacityMask": 600,
    "Opacity": 600,
    "MaskContrast": 610,
    "OpacityClipValue": 620,
    "OpacityIntensity": 630,
    "UseOpacityMask": 640,
    "UseSeparateOpacityMask": 650,
    "UseOpacityMaskOffValue": 660,
    "SubsurfaceTint": 700,
    "SubsurfaceIntensity": 710,
    "UseSubsurface": 720,
}

PARAMETER_DESCRIPTIONS.update(
    {
        "BaseColor": "基础色贴图。RGB 控制材质颜色；A 通道默认可作为 Masked 材质的镂空遮罩来源。",
        "Normal": "法线贴图。保持 Normal sampler，避免 UE 将切线空间法线当作普通颜色采样。",
        "ARM": "ARM 打包贴图。R=AO 环境遮蔽，G=Roughness 粗糙度，B=Metallic 金属度；必须使用非 sRGB / Masks 采样。",
        "ORM": "ORM 打包贴图。R=Occlusion，G=Roughness，B=Metallic；语义等同 ARM，仅命名来自不同 DCC 或烘焙工具。",
        "OpacityMask": "独立透明遮罩贴图。只有资产确实提供单独 Mask 时使用；普通道具优先使用 BaseColor.A 节省采样器。",
        "Opacity": "半透明 Opacity 贴图。用于 Translucent 材质，不等同于 Masked 的硬切遮罩。",
        "Emissive": "自发光贴图。实例中开启 UseEmissive 后才会参与 Emissive Color 输出。",
        "ImperfectionMask": "瑕疵、污渍、磨损遮罩。用于预览和材质实例调节脏污强度，不应作为颜色贴图采样。",
        "Height": "高度贴图。预留给 POM 或位移类效果；默认母材质不强制启用昂贵分支。",
        "UVTiling": "统一 UV 平铺倍数。1 表示使用模型原始 UV；增大数值会让所有贴图重复更密。",
        "BaseColorTint": "基础色染色。与 BaseColor 相乘，用于快速统一色相或做轻量变体。",
        "BaseColorIntensity": "基础色亮度倍率。建议保持在 0.5-2 范围，避免破坏 PBR 能量关系。",
        "NormalStrength": "法线强度。1 为原始法线；0 接近平面；大于 1 会增强细节但可能产生噪点。",
        "AOIntensity": "AO 强度。作用于 ARM.R；1 为贴图原值，0 会关闭贴图 AO 影响。",
        "RoughnessIntensity": "粗糙度强度。作用于 ARM.G；提高会更哑光，降低会更光滑。",
        "MetallicIntensity": "金属度强度。作用于 ARM.B；金属道具通常为 1，非金属保持 0。",
        "Specular": "非金属高光强度。常用 0.3-0.6；除非有明确材质依据，不建议极端调整。",
        "ImperfectionIntensity": "瑕疵强度。0 关闭脏污、磨损预览；提高后 ImperfectionMask 会压暗或强化表面变化。",
        "EmissiveTint": "自发光颜色染色。与 Emissive 贴图相乘，用于统一灯带或屏幕色相。",
        "EmissiveIntensity": "自发光亮度倍率。UseEmissive 开启后生效；数值越高 Bloom 越明显。",
        "MaskContrast": "遮罩对比和强度。作用于 BaseColor.A 或 OpacityMask.R；提高会让镂空边界更硬。",
        "OpacityClipValue": "Masked 剪裁阈值。高于该值的像素保留，低于该值剔除；常用 0.2-0.5。",
        "OpacityIntensity": "半透明强度倍率。用于 Opacity 贴图，不控制 Masked 镂空。",
        "UseEmissive": "自发光开关。0 输出黑色不发光；1 使用 Emissive 贴图、染色和强度参数。",
        "UseOpacityMask": "镂空遮罩总开关。0 完全不镂空；1 启用 BaseColor.A 或独立 OpacityMask 分支。",
        "UseSeparateOpacityMask": "独立遮罩开关。0 使用 BaseColor.A；1 使用 OpacityMask.R，只在存在单独遮罩贴图时开启。",
        "UseSubsurface": "次表面开关。角色皮肤材质使用；道具和硬表面默认不要开启。",
        "SubsurfaceTint": "次表面颜色。用于皮肤或半透材质的透光色调。",
        "SubsurfaceIntensity": "次表面强度。0 关闭透光感；提高后皮肤或蜡质感更明显。",
        "UseOpacityMaskOffValue": "遮罩关闭时的安全值。固定输出 1，让材质保持完全不镂空。",
        "UseEmissiveOffValue": "自发光关闭时的安全值。固定输出 0，避免实例未开启时意外发光。",
    }
)

PARAMETER_GROUPS.update(
    {
        "UseVirtualTextures": "01 UV 输入 / UV",
        "UseWorldAligned": "01 UV 输入 / UV",
        "UseTriplanar": "01 UV 输入 / UV",
        "WorldAlignedScale": "01 UV 输入 / UV",
        "ProjectionBlendSharpness": "01 UV 输入 / UV",
        "UVTiling": "01 UV 输入 / UV",
        "BaseColor": "02 基础色 / BaseColor",
        "BaseColorTint": "02 基础色 / BaseColor",
        "BaseColorIntensity": "02 基础色 / BaseColor",
        "Normal": "03 法线 / Normal",
        "NormalStrength": "03 法线 / Normal",
        "ARM": "04 ARM 打包 / PBR",
        "ORM": "04 ARM 打包 / PBR",
        "AOIntensity": "04 ARM 打包 / PBR",
        "RoughnessIntensity": "04 ARM 打包 / PBR",
        "RoughnessMin": "04 ARM 打包 / PBR",
        "RoughnessMax": "04 ARM 打包 / PBR",
        "MetallicIntensity": "04 ARM 打包 / PBR",
        "Specular": "04 ARM 打包 / PBR",
        "ImperfectionMask": "05 瑕疵 / Imperfection",
        "ImperfectionIntensity": "05 瑕疵 / Imperfection",
        "UseImperfections": "05 瑕疵 / Imperfection",
        "UseWear": "05 瑕疵 / Imperfection",
        "EdgeWearIntensity": "05 瑕疵 / Imperfection",
        "Emissive": "06 自发光 / Emissive",
        "EmissiveTint": "06 自发光 / Emissive",
        "EmissiveIntensity": "06 自发光 / Emissive",
        "UseEmissive": "06 自发光 / Emissive",
        "UseEmissiveOffValue": "06 自发光 / Emissive",
        "OpacityMask": "07 镂空 / Opacity Mask",
        "Opacity": "07 镂空 / Opacity Mask",
        "MaskContrast": "07 镂空 / Opacity Mask",
        "OpacityClipValue": "07 镂空 / Opacity Mask",
        "OpacityIntensity": "07 镂空 / Opacity Mask",
        "UseOpacityMask": "07 镂空 / Opacity Mask",
        "UseSeparateOpacityMask": "07 镂空 / Opacity Mask",
        "UseOpacityMaskOffValue": "07 镂空 / Opacity Mask",
        "Height": "08 高度 / Height",
        "HeightScale": "08 高度 / Height",
        "POMMinSteps": "08 高度 / Height",
        "POMMaxSteps": "08 高度 / Height",
        "POMTemporalAAStepMultiplier": "08 高度 / Height",
        "SubsurfaceTint": "09 次表面 / Subsurface",
        "SubsurfaceIntensity": "09 次表面 / Subsurface",
        "SkinRoughnessBias": "09 次表面 / Subsurface",
        "MicroNormalStrength": "09 次表面 / Subsurface",
        "MacroVariationScale": "09 次表面 / Subsurface",
        "MacroVariationIntensity": "09 次表面 / Subsurface",
        "UseSubsurface": "09 次表面 / Subsurface",
    }
)

LEGACY_VERBOSE_GRAPH_COMMENT_BLOCKS = [
    {
        "id": "AF_01_UV",
        "x": -1260,
        "y": -980,
        "size_x": 920,
        "size_y": 280,
        "font_size": 20,
        "text": "AF 01 UV 坐标",
        "color": (0.16, 0.32, 0.72, 0.30),
        "parameters": ["UVTiling"],
    },
    {
        "id": "AF_02_BaseColor",
        "x": -1080,
        "y": -560,
        "size_x": 1760,
        "size_y": 340,
        "font_size": 20,
        "text": "AF 02 基础色",
        "color": (0.18, 0.55, 0.36, 0.30),
        "parameters": ["BaseColor", "BaseColorTint", "BaseColorIntensity"],
    },
    {
        "id": "AF_03_Normal",
        "x": -1080,
        "y": -60,
        "size_x": 1480,
        "size_y": 300,
        "font_size": 20,
        "text": "AF 03 法线",
        "color": (0.14, 0.45, 0.68, 0.30),
        "parameters": ["Normal", "NormalStrength"],
    },
    {
        "id": "AF_04_PBR",
        "x": -1080,
        "y": 340,
        "size_x": 1520,
        "size_y": 540,
        "font_size": 20,
        "text": "AF 04 ARM 打包",
        "color": (0.78, 0.52, 0.16, 0.30),
        "parameters": ["ARM", "ORM", "AOIntensity", "RoughnessIntensity", "MetallicIntensity", "Specular"],
    },
    {
        "id": "AF_05_Imperfection",
        "x": -1080,
        "y": 900,
        "size_x": 1520,
        "size_y": 340,
        "font_size": 20,
        "text": "AF 05 瑕疵",
        "color": (0.50, 0.34, 0.72, 0.30),
        "parameters": ["ImperfectionMask", "ImperfectionIntensity", "UseImperfections", "UseWear", "EdgeWearIntensity"],
    },
    {
        "id": "AF_06_Emissive",
        "x": -1080,
        "y": 1320,
        "size_x": 1600,
        "size_y": 360,
        "font_size": 20,
        "text": "AF 06 自发光",
        "color": (0.82, 0.36, 0.14, 0.30),
        "parameters": ["Emissive", "EmissiveTint", "EmissiveIntensity", "UseEmissive", "UseEmissiveOffValue"],
    },
    {
        "id": "AF_07_Opacity",
        "x": -1080,
        "y": 1760,
        "size_x": 1700,
        "size_y": 620,
        "font_size": 20,
        "text": "AF 07 镂空遮罩",
        "color": (0.74, 0.22, 0.26, 0.30),
        "parameters": [
            "OpacityMask",
            "Opacity",
            "MaskContrast",
            "OpacityClipValue",
            "OpacityIntensity",
            "UseOpacityMask",
            "UseSeparateOpacityMask",
            "UseOpacityMaskOffValue",
        ],
    },
]

GRAPH_COMMENT_BLOCKS = [
    {
        "id": "AF_01_UV",
        "x": -1260,
        "y": -980,
        "size_x": 920,
        "size_y": 280,
        "font_size": 20,
        "text": "AF 01 UV 坐标",
        "color": (0.16, 0.32, 0.72, 0.30),
        "parameters": ["UVTiling"],
    },
    {
        "id": "AF_02_BaseColor",
        "x": -1080,
        "y": -560,
        "size_x": 1760,
        "size_y": 340,
        "font_size": 20,
        "text": "AF 02 基础色",
        "color": (0.18, 0.55, 0.36, 0.30),
        "parameters": ["BaseColor", "BaseColorTint", "BaseColorIntensity"],
    },
    {
        "id": "AF_03_Normal",
        "x": -1080,
        "y": -60,
        "size_x": 1480,
        "size_y": 300,
        "font_size": 20,
        "text": "AF 03 法线",
        "color": (0.14, 0.45, 0.68, 0.30),
        "parameters": ["Normal", "NormalStrength"],
    },
    {
        "id": "AF_04_PBR",
        "x": -1080,
        "y": 340,
        "size_x": 1520,
        "size_y": 540,
        "font_size": 20,
        "text": "AF 04 ARM 打包",
        "color": (0.78, 0.52, 0.16, 0.30),
        "parameters": ["ARM", "ORM", "AOIntensity", "RoughnessIntensity", "MetallicIntensity", "Specular"],
    },
    {
        "id": "AF_05_Imperfection",
        "x": -1080,
        "y": 900,
        "size_x": 1520,
        "size_y": 340,
        "font_size": 20,
        "text": "AF 05 瑕疵",
        "color": (0.50, 0.34, 0.72, 0.30),
        "parameters": ["ImperfectionMask", "ImperfectionIntensity", "UseImperfections", "UseWear", "EdgeWearIntensity"],
    },
    {
        "id": "AF_06_Emissive",
        "x": -1080,
        "y": 1320,
        "size_x": 1600,
        "size_y": 360,
        "font_size": 20,
        "text": "AF 06 自发光",
        "color": (0.82, 0.36, 0.14, 0.30),
        "parameters": ["Emissive", "EmissiveTint", "EmissiveIntensity", "UseEmissive", "UseEmissiveOffValue"],
    },
    {
        "id": "AF_07_Opacity",
        "x": -1080,
        "y": 1760,
        "size_x": 1700,
        "size_y": 620,
        "font_size": 20,
        "text": "AF 07 镂空遮罩",
        "color": (0.74, 0.22, 0.26, 0.30),
        "parameters": [
            "OpacityMask",
            "Opacity",
            "MaskContrast",
            "OpacityClipValue",
            "OpacityIntensity",
            "UseOpacityMask",
            "UseSeparateOpacityMask",
            "UseOpacityMaskOffValue",
        ],
    },
]


DEFAULT_VARIANTS = {
    "opaque": AF_PROPS_MASTER,
    "opaque_vt": AF_PROPS_MASTER,
    "masked": AF_PROPS_MASTER,
    "masked_vt": AF_PROPS_MASTER,
    "emissive": AF_PROPS_MASTER,
    "emissive_vt": AF_PROPS_MASTER,
    "dirty_wear": AF_PROPS_MASTER,
    "dirty_wear_vt": AF_PROPS_MASTER,
    "world_aligned": AF_ENVIRONMENT_MASTER,
    "pom": AF_ENVIRONMENT_MASTER,
    "decal": AF_PROPS_MASTER,
    "glass": AF_PROPS_MASTER,
    "translucent": AF_PROPS_MASTER,
    "translucent_vt": AF_PROPS_MASTER,
    "environment": AF_ENVIRONMENT_MASTER,
    "environment_vt": AF_ENVIRONMENT_MASTER,
    "environment_masked": AF_ENVIRONMENT_MASTER,
    "environment_masked_vt": AF_ENVIRONMENT_MASTER,
    "environment_emissive": AF_ENVIRONMENT_MASTER,
    "environment_emissive_vt": AF_ENVIRONMENT_MASTER,
    "character_basic": AF_CHARACTER_MASTER,
    "character_basic_vt": AF_CHARACTER_MASTER,
    "character_masked": AF_CHARACTER_MASTER,
    "character_masked_vt": AF_CHARACTER_MASTER,
    "emissive_surface": AF_PROPS_MASTER,
    "emissive_surface_vt": AF_PROPS_MASTER,
}


def parameter_api_mapping(names):
    """Return artist-facing API names for planned parameter names."""
    return dict((name, PARAMETER_API_MAPPING.get(name, name)) for name in names if name)


def detect_material_features(textures, profile=None):
    """Detect material features from manifest texture usages and render profile."""
    profile = profile or {}
    features = set()
    for texture in textures or []:
        usage = (texture.get("usage") or "").lower()
        parameter = texture.get("parameter", "")
        if usage in ("base_color", "albedo", "diffuse") or parameter == "BaseColor":
            features.add("base_color")
        elif usage == "normal" or parameter == "Normal":
            features.add("normal")
        elif usage in ("packed_arm", "packed_orm", "arm", "orm") or parameter in ("ARM", "ORM"):
            features.add("packed_arm")
        elif usage in ("opacity_mask", "mask") or parameter == "OpacityMask":
            features.add("opacity_mask")
        elif usage in ("opacity", "alpha") or parameter == "Opacity":
            features.add("opacity")
        elif usage in ("emissive", "emission") or parameter == "Emissive":
            features.add("emissive")
        elif usage in ("height", "height_map", "displacement", "pom") or parameter == "Height":
            features.add("height")
        elif usage in ("world_aligned", "triplanar", "projection"):
            features.add("world_aligned")
        elif usage in ("decal", "decal_color", "decal_normal"):
            features.add("decal")
        elif usage in ("glass", "transmission", "refraction"):
            features.add("glass")
        elif usage in ("imperfection_mask", "dirty", "dirt", "grime", "wear", "edge_wear", "scratches") or parameter == "ImperfectionMask":
            features.add("imperfection_mask")
        if _texture_is_virtual(texture):
            features.add("virtual_texture")

    render_mode = profile.get("render_mode", "")
    if render_mode == "masked":
        features.add("opacity_mask")
    elif render_mode == "translucent":
        features.add("opacity")
    return sorted(features)


def resolve_material_variant(profile, textures, slot_variant=None):
    """Select a prebuilt material variant from detected features."""
    profile = profile or {}
    features = detect_material_features(textures, profile)
    if slot_variant:
        return {
            "selected_master_family": profile.get("master_family", SURFACE_PBR_FAMILY),
            "selected_material_variant": profile["material_variants"][slot_variant],
            "variant_key": slot_variant,
            "detected_features": features,
            "variant_reason": "Explicit project material slot route: {0}".format(slot_variant),
        }
    feature_set = set(features)
    variants = dict(DEFAULT_VARIANTS)
    project_variants = profile.get("material_variants", {}) or {}
    variants.update(project_variants)

    family = (profile.get("asset_family") or "").lower()
    if "decal" in feature_set and _profile_allows_special_variant(profile, "decal"):
        key = "decal"
    elif "glass" in feature_set and _profile_allows_special_variant(profile, "glass"):
        key = "glass"
    elif "height" in feature_set and _profile_allows_special_variant(profile, "pom"):
        key = "pom"
    elif "world_aligned" in feature_set and _profile_allows_special_variant(profile, "world_aligned"):
        key = "world_aligned"
    elif "opacity" in feature_set and profile.get("render_mode") == "translucent":
        key = "translucent"
    elif "opacity_mask" in feature_set and profile.get("master_material") != PROPS_PAINTER_OPAQUE_MASTER:
        key = "masked"
    elif "emissive" in feature_set:
        key = "emissive"
    elif "imperfection_mask" in feature_set:
        key = "dirty_wear"
    else:
        key = "opaque"

    key = _family_variant_key(family, key, feature_set)

    if "virtual_texture" in feature_set:
        vt_key = key + "_vt"
        if vt_key in variants:
            key = vt_key

    selected = project_variants.get(key) or profile.get("master_material") or variants.get(key) or AF_HARDSURFACE_MASTER
    return {
        "selected_master_family": profile.get("master_family", SURFACE_PBR_FAMILY),
        "selected_material_variant": selected,
        "variant_key": key,
        "detected_features": features,
        "variant_reason": _variant_reason(key, features),
    }


def _variant_reason(key, features):
    if key.endswith("_vt"):
        return "detected virtual texture input; routed to the shared category master until VT sampling siblings are verified: {0}".format(", ".join(features))
    return "matched prebuilt variant from detected features: {0}".format(", ".join(features) or "none")


def _profile_allows_special_variant(profile, variant_key):
    enabled = profile.get("enabled_material_variants")
    if enabled is None:
        enabled = profile.get("allow_material_variants")
    if enabled is None:
        enabled = profile.get("allowed_special_variants")
    return variant_key in set(enabled or [])


def _family_variant_key(family, key, feature_set):
    if family == "environment":
        if key == "masked":
            return "environment_masked"
        if key == "emissive":
            return "environment_emissive"
        if key in ("opaque", "dirty_wear"):
            return "environment"
    if family == "character":
        if key == "masked":
            return "character_masked"
        if key in ("opaque", "dirty_wear", "emissive"):
            return "character_basic"
    if family == "fx" or "emissive" in feature_set and key == "emissive_surface":
        return "emissive_surface"
    return key


def _texture_is_virtual(texture):
    for key in ("effective_virtual_texture", "virtual_texture_streaming", "is_virtual_texture"):
        value = texture.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.lower() in ("true", "1", "yes", "virtual_texture"):
            return True
    actual = texture.get("actual_policy") or {}
    if isinstance(actual, dict):
        return bool(actual.get("effective_virtual_texture"))
    return False
