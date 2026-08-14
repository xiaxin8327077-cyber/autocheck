import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MODULE_COLLECTION = (
    "--collect-submodules",
    "auto_check.modules",
    "--collect-data",
    "auto_check.modules",
)
REQUIRED_HIDDEN_IMPORTS = {
    "py7zr",
    "rarfile",
    "psycopg",
    "psycopg_binary",
    "psycopg.pq",
    "pymysql",
    "sqlalchemy.dialects.mysql",
    "sqlalchemy.dialects.mysql.pymysql",
    "auto_check.resources",
    "auto_check.resources.data",
}
POWERSHELL_AST_EXTRACT = r"""
$VariableName = "__VARIABLE_NAME__"
$source = [Console]::In.ReadToEnd()
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    $source, [ref]$tokens, [ref]$errors
)
if ($errors.Count) {
    $errors | ForEach-Object { [Console]::Error.WriteLine($_.Message) }
    exit 1
}
$assignment = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
    $node.Left.VariablePath.UserPath -eq $VariableName
}, $true) | Select-Object -First 1)
if ($assignment.Count -ne 1) {
    exit 2
}
$values = @($assignment[0].Right.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
    $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst]
}, $true) | ForEach-Object {
    $literal = $_.Extent.Text
    if ($literal.Length -ge 2 -and (
        ($literal[0] -eq '"' -and $literal[$literal.Length - 1] -eq '"') -or
        ($literal[0] -eq "'" -and $literal[$literal.Length - 1] -eq "'")
    )) {
        $literal.Substring(1, $literal.Length - 2)
    } else {
        $literal
    }
})
[Console]::Out.Write(($values | ConvertTo-Json -Compress))
"""


def _read_script(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _strip_powershell_line_comments(content: str) -> str:
    """Remove PowerShell line and nested block comments without changing strings."""
    characters = []
    in_single_quote = False
    in_double_quote = False
    block_comment_depth = 0
    index = 0
    while index < len(content):
        character = content[index]
        next_character = content[index + 1] if index + 1 < len(content) else ""
        if block_comment_depth:
            if character == "<" and next_character == "#":
                block_comment_depth += 1
                index += 2
                continue
            if character == "#" and next_character == ">":
                block_comment_depth -= 1
                index += 2
                continue
            if character in "\r\n":
                characters.append(character)
            index += 1
            continue
        if in_single_quote:
            characters.append(character)
            if character == "'" and next_character == "'":
                characters.append(next_character)
                index += 2
                continue
            if character == "'":
                in_single_quote = False
        elif in_double_quote:
            characters.append(character)
            if character == "`" and next_character:
                characters.append(next_character)
                index += 2
                continue
            if character == '"':
                in_double_quote = False
        elif character == "<" and next_character == "#":
            block_comment_depth = 1
            index += 2
            continue
        elif character == "#":
            newline = content.find("\n", index)
            if newline == -1:
                break
            characters.append("\n")
            index = newline + 1
            continue
        else:
            characters.append(character)
            if character == "'":
                in_single_quote = True
            elif character == '"':
                in_double_quote = True
            elif character == "`" and next_character:
                characters.append(next_character)
                index += 2
                continue
        index += 1
    if block_comment_depth:
        raise ValueError("unterminated PowerShell block comment")
    return "".join(characters)


def _extract_powershell_array_with_ast(content: str, variable: str) -> list[str] | None:
    executable = _powershell_executable()
    if executable is None:
        return None
    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            POWERSHELL_AST_EXTRACT.replace("__VARIABLE_NAME__", variable.lstrip("$")),
        ],
        input=content,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout:
        return []
    values = json.loads(result.stdout)
    return values if isinstance(values, list) else [values]


def _extract_powershell_array(content: str, variable: str) -> list[str]:
    ast_values = _extract_powershell_array_with_ast(content, variable)
    if ast_values is not None:
        return ast_values

    return _extract_powershell_array_with_fallback(content, variable)


def _extract_powershell_array_with_fallback(content: str, variable: str) -> list[str]:
    content = _strip_powershell_line_comments(content)
    start = re.search(rf"(?m)^{re.escape(variable)}\s*=\s*@\(\s*$", content)
    assert start, f"{variable} parameter array not found"
    end = re.search(r"(?m)^\)", content[start.end() :])
    assert end, f"{variable} parameter array is not closed"
    return re.findall(r'"([^"]+)"', content[start.end() : start.end() + end.start()])


def _extract_shell_array(content: str, variable: str) -> list[str]:
    start = re.search(rf"(?m)^{re.escape(variable)}=\(\s*$", content)
    assert start, f"{variable} parameter array not found"
    end = re.search(r"(?m)^\)", content[start.end() :])
    assert end, f"{variable} parameter array is not closed"
    return shlex.split(
        content[start.end() : start.end() + end.start()], comments=True, posix=True
    )


def _strip_shell_comment_lines(content: str) -> str:
    return "\n".join(
        line for line in content.splitlines() if not line.lstrip().startswith("#")
    )


def _extract_shell_command(content: str, command_start: str) -> list[str]:
    content = _strip_shell_comment_lines(content)
    start = content.index(command_start)
    end = content.find("\n\n", start)
    if end == -1:
        end = len(content)
    return shlex.split(content[start:end].replace("\\\n", " "), comments=True, posix=True)


def _extract_powershell_command(content: str, command_start: str) -> list[str]:
    return _extract_shell_command(_strip_powershell_line_comments(content), command_start)


def _assert_module_collection(arguments: list[str]) -> None:
    assert any(
        tuple(arguments[index : index + len(MODULE_COLLECTION)]) == MODULE_COLLECTION
        for index in range(len(arguments) - len(MODULE_COLLECTION) + 1)
    )


def _option_values(arguments: list[str], option: str) -> list[str]:
    values = [
        arguments[index + 1]
        for index, argument in enumerate(arguments[:-1])
        if argument == option
    ]
    assert values, f"{option} is missing"
    return values


def _assert_existing_assets_and_hidden_imports(
    arguments: list[str], separator: str, hidden_imports: set[str]
) -> None:
    data_values = _option_values(arguments, "--add-data")
    assert any(value.endswith(f"{separator}auto_check/web") for value in data_values)
    assert any(value.endswith(f"{separator}auto_check/resources") for value in data_values)
    for module_name in hidden_imports:
        assert module_name in _option_values(arguments, "--hidden-import")


def test_powershell_comment_only_module_options_do_not_satisfy_collection():
    content = """\
$pyinstallerArgs = @(
  "--noconfirm"
  # "--collect-submodules", "auto_check.modules",
  # "--collect-data", "auto_check.modules",
)
& $python @pyinstallerArgs
"""

    with pytest.raises(AssertionError):
        _assert_module_collection(_extract_powershell_array(content, "$pyinstallerArgs"))


def test_powershell_block_comment_only_module_options_do_not_satisfy_fallback():
    content = """\
$pyinstallerArgs = @(
  "--noconfirm",
  <#
  "--collect-submodules", "auto_check.modules",
  <# "--collect-data", "auto_check.modules", #>
  "--collect-data", "auto_check.modules",
  #>
  "--onefile"
)
"""

    with pytest.raises(AssertionError):
        _assert_module_collection(
            _extract_powershell_array_with_fallback(content, "$pyinstallerArgs")
        )


def test_powershell_fallback_rejects_unterminated_block_comments():
    with pytest.raises(ValueError, match="unterminated PowerShell block comment"):
        _extract_powershell_array_with_fallback(
            '$pyinstallerArgs = @( <# "--collect-submodules" )',
            "$pyinstallerArgs",
        )


def test_powershell_comment_stripping_preserves_hashes_in_string_literals():
    content = """\
$pyinstallerArgs = @(
  "--add-data", "C:/assets#release;auto_check/web" # explanatory comment
)
"""

    stripped = _strip_powershell_line_comments(content)
    assert "C:/assets#release;auto_check/web" in stripped
    assert "explanatory comment" not in stripped
    assert "C:/assets#release;auto_check/web" in _extract_powershell_array(
        content, "$pyinstallerArgs"
    )


def test_powershell_fallback_preserves_comment_symbols_and_escapes_in_strings():
    content = """\
$pyinstallerArgs = @(
  "C:/assets/<#release#>/#tag",
  'single <# #> # quote '' preserved',
  "double `" <# #> # preserved"
)
<# ignored block comment #>
"""

    stripped = _strip_powershell_line_comments(content)
    assert "C:/assets/<#release#>/#tag" in stripped
    assert "single <# #> # quote '' preserved" in stripped
    assert 'double `" <# #> # preserved' in stripped
    assert "ignored block comment" not in stripped


def test_shell_comment_only_module_options_do_not_satisfy_collection():
    content = """\
# python -m PyInstaller --collect-submodules auto_check.modules --collect-data auto_check.modules
python -m PyInstaller \\
  --noconfirm # --collect-submodules auto_check.modules --collect-data auto_check.modules
"""

    with pytest.raises(AssertionError):
        _assert_module_collection(
            _extract_shell_command(content, "python -m PyInstaller")
        )


def test_package_windows_collects_modules_in_the_invoked_parameter_array():
    content = _read_script("package-windows.ps1")
    assert re.search(
        r"(?m)^& \$python @pyinstallerArgs$", _strip_powershell_line_comments(content)
    )
    arguments = _extract_powershell_array(content, "$pyinstallerArgs")

    _assert_module_collection(arguments)
    _assert_existing_assets_and_hidden_imports(
        arguments,
        ";",
        REQUIRED_HIDDEN_IMPORTS,
    )


def test_package_linux_collects_modules_in_the_invoked_parameter_array():
    content = _read_script("package-linux.sh")
    assert '"$PYTHON" "${PYINSTALLER_ARGS[@]}"' in _strip_shell_comment_lines(content)
    arguments = _extract_shell_array(content, "PYINSTALLER_ARGS")

    _assert_module_collection(arguments)
    _assert_existing_assets_and_hidden_imports(
        arguments,
        ":",
        REQUIRED_HIDDEN_IMPORTS,
    )


def test_linux_build_dockerfile_collects_modules_in_the_pyinstaller_command():
    arguments = _extract_shell_command(
        _read_script("Dockerfile.linux-build"), "RUN pyinstaller --noconfirm"
    )

    _assert_module_collection(arguments)
    _assert_existing_assets_and_hidden_imports(
        arguments,
        ":",
        REQUIRED_HIDDEN_IMPORTS,
    )


def test_docker_build_collects_modules_in_the_pyinstaller_command():
    arguments = _extract_shell_command(
        _read_script("docker-build.sh"), "python3.12 -m PyInstaller"
    )

    _assert_module_collection(arguments)
    _assert_existing_assets_and_hidden_imports(
        arguments,
        ":",
        REQUIRED_HIDDEN_IMPORTS,
    )


def test_root_spec_collects_modules_data_and_required_hidden_imports():
    content = (ROOT / "auto-check.spec").read_text(encoding="utf-8")

    assert "collect_submodules('auto_check.modules')" in content
    assert "collect_data_files('auto_check.modules')" in content
    for module_name in REQUIRED_HIDDEN_IMPORTS:
        assert repr(module_name) in content


def test_packaging_entrypoints_run_the_built_artifact_smoke_test():
    assert '& $exe --package-smoke-test' in _read_script("package-windows.ps1")
    assert '"$OUTPUT" --package-smoke-test' in _read_script("package-linux.sh")
    assert 'RUN /output/auto-check --package-smoke-test' in _read_script(
        "Dockerfile.linux-build"
    )
    assert '"$OUTPUT_DIR/auto-check" --package-smoke-test' in _read_script(
        "docker-build.sh"
    )


def test_module_collection_can_resolve_the_src_package_before_pyinstaller_runs():
    spec = (ROOT / "auto-check.spec").read_text(encoding="utf-8")
    assert "sys.path.insert(0, str(SRC))" in spec
    assert spec.index("sys.path.insert(0, str(SRC))") < spec.index(
        "collect_data_files('auto_check.modules')"
    )

    linux_script = _read_script("package-linux.sh")
    assert 'export PYTHONPATH="$SRC_PATH${PYTHONPATH:+:$PYTHONPATH}"' in linux_script
    assert linux_script.index("export PYTHONPATH=") < linux_script.index(
        '"$PYTHON" "${PYINSTALLER_ARGS[@]}"'
    )


def test_legacy_windows_build_collects_modules_in_the_pyinstaller_command():
    arguments = _extract_powershell_command(
        _read_script("build.ps1"), "& $python -m PyInstaller --noconfirm"
    )

    _assert_module_collection(arguments)
    data_values = _option_values(arguments, "--add-data")
    assert any(value.endswith(";auto_check/web") for value in data_values)
    assert any(value.endswith(";auto_check/resources") for value in data_values)
