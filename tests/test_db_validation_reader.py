from auto_check.db_validation.reader import ValidationTableReader


class FakeConfig:
    def __init__(self, db_type):
        self.db_type = db_type
        self.schema = "dws"
        self.database = "autocheck"


class FakeClient:
    def __init__(self, db_type):
        self.config = FakeConfig(db_type)
        self.sql = ""

    def fetch_all(self, sql, params=()):
        self.sql = sql
        return []


def test_reader_decrypts_zg07_borrower_code_for_postgresql():
    client = FakeClient("postgresql")

    ValidationTableReader(client).fetch_table("zgxgzh_ioudetail_zg07")

    assert "public.decrypt" in client.sql
    assert "decode(convert_from(\"debtorcode\", 'UTF8'), 'hex')" in client.sql
    assert "'JsxtConsole', 'aes'" in client.sql
    assert "AS \"debtorcode\"" in client.sql
    assert "FROM \"dws\".\"zgxgzh_ioudetail_zg07\"" in client.sql


def test_reader_decrypts_zg07_previous_borrower_code_for_mysql():
    client = FakeClient("mysql")

    ValidationTableReader(client).fetch_table("zgxgzh_ioudetail_zg07_2026_05")

    assert "AES_DECRYPT(UNHEX(`debtorcode`), 'JsxtConsole')" in client.sql
    assert "AS `debtorcode`" in client.sql
    assert "FROM `dws`.`zgxgzh_ioudetail_zg07_2026_05`" in client.sql


def test_reader_leaves_other_tables_as_plain_select():
    client = FakeClient("postgresql")

    ValidationTableReader(client).fetch_table("zgxgzh_baseinfo_zg01_26")

    assert client.sql == "SELECT * FROM \"dws\".\"zgxgzh_baseinfo_zg01_26\""
