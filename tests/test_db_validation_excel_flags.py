from datetime import date

from auto_check.db_validation.excel import result_filename


def test_result_filename_marks_template_check_when_enabled():
    assert result_filename(date(2026, 5, 31), enable_template_check=True) == (
        "20260531-资管产品数据审核结果-模板校验（是）-公开信息校验（否）(Ver.20260202).xlsx"
    )
