import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from cwh_project_config import resolve_agenda_order


def save(root, confirmed=True, evidence='User explicitly confirmed this project convention'):
    path = root / 'cwh_project.json'
    path.write_text(json.dumps({'schema_version': 1, 'numbered_child_agenda_order': {
        'confirmed': confirmed, 'confirmation_evidence': evidence}}), encoding='utf-8')
    return path


def test_unconfigured_project_does_not_inherit_other_project(tmp_path):
    save(tmp_path)
    unrelated = tmp_path / 'other'
    unrelated.mkdir()
    assert resolve_agenda_order(cwd=unrelated)['confirmed'] is False


def test_automatic_project_confirmation_with_receipt(tmp_path):
    path = save(tmp_path)
    result = resolve_agenda_order(cwd=tmp_path)
    assert result['confirmed'] is True
    assert result['basis'] == 'project_config'
    assert result['config_path'] == str(path)
    assert len(result['config_sha256']) == 64


def test_explicit_path_survives_isolated_worker_cwd(tmp_path):
    path = save(tmp_path)
    other = tmp_path / 'worker'
    other.mkdir()
    assert resolve_agenda_order(config_path=str(path), cwd=other)['confirmed'] is True


@pytest.mark.parametrize('explicit', [True, False])
def test_cli_can_override_saved_convention(tmp_path, explicit):
    save(tmp_path, not explicit)
    assert resolve_agenda_order(explicit, cwd=tmp_path)['confirmed'] is explicit


@pytest.mark.parametrize('confirmed,evidence', [('true', 'user'), (1, 'user'), (True, '')])
def test_invalid_confirmation_rejected(tmp_path, confirmed, evidence):
    save(tmp_path, confirmed, evidence)
    with pytest.raises(ValueError):
        resolve_agenda_order(cwd=tmp_path)


def test_explicit_missing_config_is_not_silently_ignored(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_agenda_order(config_path=str(tmp_path / 'missing.json'))


def test_pipeline_freezes_confirmation_in_new_contract(tmp_path, monkeypatch):
    from run_cwh_resumable_pipeline import parser, contract_from_args
    save(tmp_path)
    monkeypatch.chdir(tmp_path)
    args = parser().parse_args(['run', '--job-dir', str(tmp_path / 'job')])
    contract = contract_from_args(args)
    assert contract['agenda_order_confirmed'] is True
    assert contract['agenda_order_confirmation']['basis'] == 'project_config'
    save(tmp_path, False)
    assert contract['agenda_order_confirmed'] is True
    assert contract_from_args(args)['agenda_order_confirmed'] is False
