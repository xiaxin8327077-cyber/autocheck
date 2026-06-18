from __future__ import annotations

import zipfile

import pytest

from auto_check.app.pbc_import import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    TableColumn,
    _display_zip_name,
    build_column_mappings,
    inspect_import_upload,
    inspect_import_upload_with_target_columns,
    inspect_zip_headers,
    iter_mapped_rows,
    iter_projected_rows,
    mapped_target_columns,
    parse_table_ref,
)


def _write_zip(path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content.encode("utf-8-sig"))


def test_supported_upload_extensions_include_archives_and_single_files():
    assert {".zip", ".rar", ".7z", ".xlsx", ".xls", ".csv"} <= SUPPORTED_UPLOAD_EXTENSIONS


def test_inspect_import_upload_reads_single_csv_file(tmp_path):
    upload = tmp_path / "public_information.csv"
    upload.write_text("产品代码,产品名称\nP1,产品一\n", encoding="utf-8-sig")

    inspection = inspect_import_upload(upload)

    assert inspection.columns == ["产品代码", "产品名称"]
    assert [(file.name, file.file_type, file.columns) for file in inspection.files] == [
        ("public_information.csv", "csv", ["产品代码", "产品名称"])
    ]


def test_iter_mapped_rows_reads_single_csv_file(tmp_path):
    upload = tmp_path / "public_information.csv"
    upload.write_text("信息类型名称,产品代码,发行机构名称\n公募基金,P1,机构一\n", encoding="utf-8-sig")
    mappings = [
        TableColumn("info_type_name", "信息类型名称"),
        TableColumn("product_code", "产品代码"),
    ]
    column_mappings = build_column_mappings(["信息类型名称", "产品代码", "发行机构名称"], mappings)

    rows = list(iter_mapped_rows(upload, column_mappings))

    assert rows == [("公募基金", "P1")]


def test_import_upload_detects_header_after_title_rows_and_skips_blank_header_columns(tmp_path):
    upload = tmp_path / "template.csv"
    upload.write_text(
        "\n"
        "金融机构资管产品模板数据修改申请报备表,,,\n"
        "\n"
        "序号,机构名称,,产品品种\n"
        "1,江苏省国际信托有限责任公司,,02-信托公司资管产品\n",
        encoding="utf-8-sig",
    )

    inspection = inspect_import_upload(upload)
    rows = list(iter_projected_rows(upload, columns=inspection.columns, file_layouts=inspection.files))

    assert inspection.columns == ["序号", "机构名称", "产品品种"]
    assert inspection.files[0].header_row == 4
    assert inspection.files[0].data_start_row == 5
    assert inspection.files[0].detection == "smart"
    assert rows == [("1", "江苏省国际信托有限责任公司", "02-信托公司资管产品")]


def test_inspect_zip_headers_reads_csv_columns_in_first_seen_order(tmp_path):
    archive = tmp_path / "pbc.zip"
    _write_zip(
        archive,
        {
            "基金.csv": "产品代码,产品名称,剔除列\nP1,产品一,X\n",
            "信托.csv": "产品代码,新增列,产品名称\nP2,Y,产品二\n",
        },
    )

    inspection = inspect_zip_headers(archive)

    assert [file.name for file in inspection.files] == ["基金.csv", "信托.csv"]
    assert inspection.columns == ["产品代码", "产品名称", "剔除列", "新增列"]
    assert inspection.files[0].columns == ["产品代码", "产品名称", "剔除列"]


def test_inspect_zip_headers_ignores_executable_payloads(tmp_path):
    archive = tmp_path / "pbc.zip"
    _write_zip(
        archive,
        {
            "fund.csv": "产品代码,产品名称\nP1,产品一\n",
            "payload.exe": "not executable here",
            "script.bat": "echo bad",
        },
    )

    inspection = inspect_zip_headers(archive)

    assert [file.name for file in inspection.files] == ["fund.csv"]
    assert inspection.columns == ["产品代码", "产品名称"]


def test_inspect_zip_headers_displays_file_names_without_archive_folders(tmp_path):
    archive = tmp_path / "pbc.zip"
    _write_zip(
        archive,
        {
            "SPV代码20260601/资管产品公开信息查询结果_保险资管产品.csv": "产品代码,产品名称\nP1,产品一\n",
            "嵌套目录/资管产品公开信息查询结果_基金产品.csv": "产品代码,产品名称\nP2,产品二\n",
        },
    )

    inspection = inspect_zip_headers(archive)

    assert [file.name for file in inspection.files] == [
        "资管产品公开信息查询结果_保险资管产品.csv",
        "资管产品公开信息查询结果_基金产品.csv",
    ]


def test_display_zip_name_recovers_gbk_encoded_zip_file_names():
    raw_name = "SPV代码20260601/资管产品公开信息查询结果_保险资管产品.csv".encode("gbk")
    stored_name = raw_name.decode("cp437")
    info = zipfile.ZipInfo(stored_name)
    info.flag_bits = 0

    assert _display_zip_name(info) == "SPV代码20260601/资管产品公开信息查询结果_保险资管产品.csv"


def test_inspect_zip_headers_prefers_header_encoding_when_later_rows_have_bad_bytes(tmp_path):
    archive = tmp_path / "pbc.zip"
    content = "信息类型名称,产品代码,发行机构名称\n".encode("utf-8-sig") + b"\xff,CP001,\xff\n"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("基金.csv", content)

    inspection = inspect_zip_headers(archive)

    assert inspection.columns[:3] == ["信息类型名称", "产品代码", "发行机构名称"]


def test_iter_projected_rows_drops_and_reorders_columns(tmp_path):
    archive = tmp_path / "pbc.zip"
    _write_zip(
        archive,
        {
            "基金.csv": "产品代码,产品名称,剔除列\nP1,产品一,X\n",
            "信托.csv": "产品代码,产品名称,剔除列\nP2,产品二,Y\n",
        },
    )

    rows = list(iter_projected_rows(archive, columns=["产品代码", "产品名称", "剔除列"], drop_columns=["剔除列"], column_order=["产品名称", "产品代码"]))

    assert rows == [("产品一", "P1"), ("产品二", "P2")]


def test_build_column_mappings_matches_source_columns_to_target_comments():
    mappings = build_column_mappings(
        ["信息类型名称", "产品代码", "发行机构名称", "不存在列"],
        [
            TableColumn("info_type_name", "信息类型名称"),
            TableColumn("product_code", "产品代码"),
            TableColumn("issuer_name", "发行机构名称"),
        ],
    )

    assert [(m.source_column, m.target_column) for m in mappings] == [
        ("信息类型名称", "info_type_name"),
        ("产品代码", "product_code"),
        ("发行机构名称", "issuer_name"),
        ("不存在列", ""),
    ]


def test_iter_mapped_rows_uses_source_columns_but_outputs_target_order(tmp_path):
    archive = tmp_path / "pbc.zip"
    _write_zip(
        archive,
        {"基金.csv": "信息类型名称,产品代码,发行机构名称\n公募基金,P1,机构一\n"},
    )
    mappings = build_column_mappings(
        ["信息类型名称", "产品代码", "发行机构名称"],
        [
            TableColumn("product_code", "产品代码"),
            TableColumn("info_type_name", "信息类型名称"),
        ],
    )

    columns = mapped_target_columns(mappings)
    rows = list(iter_mapped_rows(archive, mappings))

    assert columns == ["info_type_name", "product_code"]
    assert rows == [("公募基金", "P1")]


def test_iter_mapped_rows_fills_missing_source_columns_with_none(tmp_path):
    archive = tmp_path / "pbc.zip"
    _write_zip(
        archive,
        {
            "fund.csv": "Product Code,Product Name\nP1,Fund One\n",
            "trust.csv": "Product Code\nP2\n",
        },
    )
    mappings = build_column_mappings(
        ["Product Code", "Product Name"],
        [
            TableColumn("product_code", "Product Code"),
            TableColumn("product_name", "Product Name"),
        ],
    )

    assert list(iter_mapped_rows(archive, mappings)) == [("P1", "Fund One"), ("P2", None)]


def test_target_columns_detect_title_area_and_read_rows_from_content_area(tmp_path):
    upload = tmp_path / "public_information.csv"
    upload.write_text("公开信息报表\nProduct Code,Product Name\nP1,Fund One\n", encoding="utf-8-sig")
    target_columns = [
        TableColumn("product_code", "Product Code"),
        TableColumn("product_name", "Product Name"),
    ]

    inspection = inspect_import_upload_with_target_columns(upload, target_columns)
    mappings = build_column_mappings(inspection.columns, target_columns)
    rows = list(iter_mapped_rows(upload, mappings, file_layouts=inspection.files))

    assert inspection.columns == ["Product Code", "Product Name"]
    assert inspection.files[0].header_row == 2
    assert inspection.files[0].data_start_row == 3
    assert inspection.files[0].detection == "smart"
    assert rows == [("P1", "Fund One")]


def test_target_columns_detect_header_after_long_blank_template_area(tmp_path):
    upload = tmp_path / "public_information.csv"
    upload.write_text(("\n" * 24) + "Product Code,Product Name\nP1,Fund One\n", encoding="utf-8-sig")
    target_columns = [
        TableColumn("product_code", "Product Code"),
        TableColumn("product_name", "Product Name"),
    ]

    inspection = inspect_import_upload_with_target_columns(upload, target_columns)
    mappings = build_column_mappings(inspection.columns, target_columns)
    rows = list(iter_mapped_rows(upload, mappings, file_layouts=inspection.files))

    assert inspection.columns == ["Product Code", "Product Name"]
    assert inspection.files[0].header_row == 25
    assert inspection.files[0].data_start_row == 26
    assert inspection.files[0].detection == "smart"
    assert rows == [("P1", "Fund One")]


def test_target_columns_fall_back_to_generic_header_when_no_target_matches(tmp_path):
    upload = tmp_path / "public_information.csv"
    upload.write_text("Template Title\nExternal Key,External Label\nP1,Fund One\n", encoding="utf-8-sig")
    target_columns = [
        TableColumn("product_code", "Product Code"),
        TableColumn("product_name", "Product Name"),
    ]

    inspection = inspect_import_upload_with_target_columns(upload, target_columns)
    mappings = build_column_mappings(inspection.columns, target_columns)

    assert inspection.columns == ["External Key", "External Label"]
    assert inspection.files[0].header_row == 2
    assert inspection.files[0].data_start_row == 3
    assert inspection.files[0].detection == "smart"
    assert [(mapping.source_column, mapping.target_column) for mapping in mappings] == [
        ("External Key", ""),
        ("External Label", ""),
    ]


def test_default_header_with_exact_target_match_skips_smart_detection(tmp_path):
    upload = tmp_path / "public_information.csv"
    upload.write_text("Product Code,报表标题\nP1,Fund One\n", encoding="utf-8-sig")
    target_columns = [
        TableColumn("product_code", "Product Code"),
        TableColumn("product_name", "Product Name"),
    ]

    inspection = inspect_import_upload_with_target_columns(upload, target_columns)

    assert inspection.columns == ["Product Code", "报表标题"]
    assert inspection.files[0].header_row == 1
    assert inspection.files[0].data_start_row == 2
    assert inspection.files[0].detection == "default"


def test_parse_table_ref_accepts_dotted_identifiers_and_rejects_unsafe_text():
    table = parse_table_ref("dws.aainfo")

    assert table.parts == ("dws", "aainfo")
    assert table.quoted("postgresql") == '"dws"."aainfo"'
    assert table.quoted("mysql") == "`dws`.`aainfo`"

    for value in ["", "dws.aainfo;drop table x", "dws..aainfo", "dws.*"]:
        with pytest.raises(ValueError):
            parse_table_ref(value)
