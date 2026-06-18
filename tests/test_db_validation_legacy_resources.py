from auto_check.db_validation.legacy_resources import get_non_county_level_area_codes, get_org_info


def test_legacy_area_codes_are_loaded_from_packaged_filename_workbook():
    codes = get_non_county_level_area_codes()

    assert "110100" in codes
    assert "320100" in codes
    assert "120100" not in codes
    assert "133100" not in codes
    assert "310100" not in codes


def test_legacy_ref_info_is_loaded_from_packaged_workbook():
    info = get_org_info("D1003632000013")

    assert info.org_code == "D1003632000013"
    assert info.org_name == "\u6c5f\u82cf\u7701\u56fd\u9645\u4fe1\u6258\u6709\u9650\u8d23\u4efb\u516c\u53f8"
    assert info.manager_org == "\u5357\u4eac"
