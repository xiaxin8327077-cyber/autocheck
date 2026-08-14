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


def test_reader_decrypts_requested_column_for_postgresql():
    client = FakeClient("postgresql")

    ValidationTableReader(client).fetch_table("zg07_detail_new", decrypt_column="jkrcode")

    assert "public.decrypt" in client.sql
    assert "decode(convert_from(\"jkrcode\", 'UTF8'), 'hex')" in client.sql
    assert "'JsxtConsole', 'aes'" in client.sql
    assert "AS \"jkrcode\"" in client.sql
    assert "FROM \"dws\".\"zg07_detail_new\"" in client.sql


def test_reader_decrypts_requested_column_for_mysql():
    client = FakeClient("mysql")

    ValidationTableReader(client).fetch_table("zg07_detail_new_2026_05", decrypt_column="jkrcode")

    assert "AES_DECRYPT(UNHEX(`jkrcode`), 'JsxtConsole')" in client.sql
    assert "AS `jkrcode`" in client.sql
    assert "FROM `dws`.`zg07_detail_new_2026_05`" in client.sql


def test_reader_leaves_tables_without_decrypt_column_as_plain_select():
    client = FakeClient("postgresql")

    ValidationTableReader(client).fetch_table("zg01_detail_new")

    assert client.sql == "SELECT * FROM \"dws\".\"zg01_detail_new\""
