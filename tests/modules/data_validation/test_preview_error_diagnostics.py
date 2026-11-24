import re
from types import SimpleNamespace

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST
from tests.modules.data_validation.support import user


def dispatch(error):
    def preview(*args, **kwargs):
        raise error
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: SimpleNamespace(preview_candidate=preview))
    return router.dispatch(ModuleRequest(method='POST', path=MANIFEST.api_prefix+'/ai/preview',
        path_params={}, query={}, body={}, current_user=user(role='admin')))


def test_unexpected_preview_failure_has_safe_trace_and_reference(caplog):
    response = dispatch(RuntimeError('never-log-this-SQL-or-secret'))
    assert response.status == 500
    error = response.body['error']
    assert isinstance(error, dict) and error['code'] == 'PREVIEW_FAILED'
    assert re.fullmatch('[0-9a-f]{12}', error['reference'])
    assert error['reference'] in caplog.text and 'RuntimeError' in caplog.text
    assert 'test_preview_error_diagnostics.py:' in caplog.text
    assert 'never-log-this' not in caplog.text and 'never-log-this' not in str(error)


def test_known_preview_context_error_keeps_its_existing_status():
    response = dispatch(AppError('ANALYSIS_CONTEXT_CHANGED'))
    assert response.status == 409 and response.body['error']['code'] == 'ANALYSIS_CONTEXT_CHANGED'
