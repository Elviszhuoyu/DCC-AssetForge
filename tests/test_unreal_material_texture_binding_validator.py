from asset_forge.shared.report_schema import summarize_pipeline
from asset_forge.unreal.material_texture_binding_validator import validate_material_texture_bindings


def test_errors_when_material_instance_would_fall_back_to_default_textures():
    report = validate_material_texture_bindings(
        {
            "profile": "Props_Opaque_PainterUE_ARM",
            "materials": [
                {
                    "material_name": "B_a1",
                    "target_asset_path": "/Game/Props/Materials/MI_B_a1",
                    "texture_parameters": {},
                    "slots": {},
                }
            ],
        },
        texture_import_plan={"textures": []},
        material_parameter_report={"texture_parameters": []},
        imported_textures=[],
    )

    assert report["status"] == "error"
    assert report["can_accept"] is False
    assert any(item["id"] == "material_required_textures_missing" for item in report["errors"])
    assert any(item["id"] == "required_texture_parameter_missing" and item["parameter"] == "BaseColor" for item in report["errors"])
    assert any(item["id"] == "required_texture_parameter_missing" and item["parameter"] == "Normal" for item in report["errors"])


def test_errors_when_planned_texture_was_not_imported():
    report = validate_material_texture_bindings(
        {
            "profile": "Props_Opaque_PainterUE_ARM",
            "materials": [
                {
                    "material_name": "B_b1",
                    "target_asset_path": "/Game/Props/Materials/MI_B_b1",
                    "texture_parameters": {
                        "BaseColor": "/Game/Props/Textures/T_B_b1_BaseColor",
                        "Normal": "/Game/Props/Textures/T_B_b1_Normal",
                    },
                    "slots": {
                        "base_color": "/Game/Props/Textures/T_B_b1_BaseColor",
                        "normal": "/Game/Props/Textures/T_B_b1_Normal",
                    },
                }
            ],
        },
        texture_import_plan={
            "textures": [
                {"target_asset_path": "/Game/Props/Textures/T_B_b1_BaseColor"},
                {"target_asset_path": "/Game/Props/Textures/T_B_b1_Normal"},
            ]
        },
        material_parameter_report={
            "texture_parameters": [
                {
                    "material_instance_path": "/Game/Props/Materials/MI_B_b1",
                    "name": "BaseColor",
                    "applied": True,
                    "texture_asset_path": "/Game/Props/Textures/T_B_b1_BaseColor",
                },
                {
                    "material_instance_path": "/Game/Props/Materials/MI_B_b1",
                    "name": "Normal",
                    "applied": False,
                    "texture_asset_path": "/Game/Props/Textures/T_B_b1_Normal",
                },
            ]
        },
        imported_textures=["/Game/Props/Textures/T_B_b1_BaseColor"],
    )

    assert report["status"] == "error"
    assert report["can_accept"] is False
    assert any(item["id"] == "texture_asset_exists" and item["parameter"] == "Normal" for item in report["errors"])
    assert any(item["id"] == "material_instance_texture_parameter_applied" and item["parameter"] == "Normal" for item in report["errors"])


def test_pipeline_summary_includes_material_texture_binding_errors():
    summary = summarize_pipeline(
        import_report={
            "status": "success",
            "material_texture_binding_validation": {
                "status": "error",
                "checks": [
                    {
                        "id": "required_texture_parameter_missing",
                        "status": "error",
                        "message": "材质 B_a1 缺少必需贴图 base_color->BaseColor，导入后会使用默认贴图。",
                    }
                ],
                "warnings": [],
                "errors": [{"id": "required_texture_parameter_missing"}],
            },
        }
    )

    assert summary["material_texture_binding_status"] == "error"
    assert summary["material_texture_binding_error_count"] == 1
    assert any(item["source"] == "material_texture_binding" for item in summary["errors"])
