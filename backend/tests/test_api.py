import pytest
from fastapi.testclient import TestClient

from src.config.database import Session
from src.config.runtime import get_redis
from src.main import app
from src.models.observation import Observation
from src.models.study import Study
from src.models.user import User
from src.utils.security import hash_password

PASSWORD = 'Research2026!'


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    with Session() as db:
        for role in ('admin', 'analyst', 'viewer'):
            if not db.query(User).filter_by(email=f'{role}@demo.local').first():
                db.add(User(email=f'{role}@demo.local', role=role, password_hash=hash_password(PASSWORD)))
        db.commit()
    tokens = {}
    for role in ('admin', 'analyst', 'viewer'):
        response = client.post('/auth/login', json={'email': f'{role}@demo.local', 'password': PASSWORD})
        assert response.status_code == 200, response.text
        tokens[role] = response.json()['token']
    return {role: {'Authorization': f'Bearer {token}'} for role, token in tokens.items()}


def add_study(values):
    with Session() as db:
        study = Study(name='青禾·接口受保护', source_filename='api.csv', description='api')
        db.add(study)
        db.flush()
        for i, value in enumerate(values):
            db.add(Observation(study_id=study.id, source_key=f'A-{i:03d}',
                               values={'moisture': value, 'extract': 30.0}))
        db.commit()
        return study.id


def test_viewer_hides_values_counts_and_exact_runs(client, auth):
    study_id = add_study([1.0, 2.0, 3.5, 4.5, 5.5, 6.5, 7.5])
    exact = client.post('/runs', headers=auth['analyst'],
                        json={'study_id': study_id, 'name': '历史精确研究', 'parameters': {}})
    assert exact.status_code == 200, exact.text
    run_id = exact.json()['id']
    # Analyst-triggered exact run is completed synchronously in this test.
    with Session() as db:
        from src.models.run import Run
        from src.services.algorithm import calculate
        run = db.get(Run, run_id)
        run.status = 'completed'
        run.result = calculate(run.snapshot, run.parameters)
        db.commit()

    client.post(f'/studies/{study_id}/protection', headers=auth['admin'],
                json={'total_epsilon': 2.0, 'bins': [0, 2, 4, 6, 8, 100]})

    listed = client.get('/studies', headers=auth['viewer']).json()
    entry = next(x for x in listed if x['id'] == study_id)
    assert entry['protected'] is True and entry['row_count'] is None

    rows = client.get(f'/studies/{study_id}/observations', headers=auth['viewer']).json()
    assert rows == []  # not even the exact number of rows is disclosed
    assert client.get(f'/studies/{study_id}/observations', headers=auth['analyst']).json()

    overview = client.get('/overview', headers=auth['viewer']).json()
    assert all(x['study_id'] != study_id for x in overview['runs'])
    assert all(x['study_id'] != study_id for x in client.get('/runs', headers=auth['viewer']).json())
    audits = client.get('/audits', headers=auth['viewer']).json()
    # Only protected-release events remain for this batch; the earlier
    # observation saves and exact-run queue entries are gone.
    assert {x['action'] for x in audits if x['study_id'] == study_id} == {'protection.policy'}
    assert all('A-' not in x['detail'] for x in audits)
    assert client.get(f'/studies/{study_id}/observations', headers=auth['admin']).json()

    assert client.get(f'/runs/{run_id}', headers=auth['viewer']).status_code == 403
    assert client.get(f'/runs/{run_id}/export', headers=auth['viewer']).status_code == 403
    # Analysts keep access to the exact research they are allowed to perform.
    assert client.get(f'/runs/{run_id}', headers=auth['analyst']).status_code == 200


def test_viewer_sees_pending_then_available_release(client, auth):
    study_id = add_study([1.0, 2.5, 3.0, 4.5, 5.5, 6.5, 7.5, 9.0])
    client.post(f'/studies/{study_id}/protection', headers=auth['admin'],
                json={'total_epsilon': 1.0, 'bins': [0, 2, 4, 6, 8, 100]})
    created = client.post(f'/studies/{study_id}/protected-releases', headers=auth['admin'],
                          json={'name': '观察员受保护分布', 'epsilon': 0.5})
    assert created.status_code == 200, created.text
    release_id = created.json()['id']
    pending = client.get(f'/protected-releases/{release_id}', headers=auth['viewer']).json()
    assert pending['status'] == 'pending' and pending['result'] is None and pending['downloadable'] is False
    assert client.get(f'/protected-releases/{release_id}/export', headers=auth['viewer']).status_code == 409

    from src.services.protection import process_release
    while get_redis().lpop('protected-queue'):
        pass
    process_release(release_id, session_factory=Session)

    available = client.get(f'/protected-releases/{release_id}', headers=auth['viewer']).json()
    assert available['status'] == 'available' and available['downloadable'] is True
    assert available['result']['counts'] and 'snapshot' not in available and 'fingerprint' not in available
    csv = client.get(f'/protected-releases/{release_id}/export', headers=auth['viewer'])
    assert csv.status_code == 200 and csv.text.strip()

    spent = client.get(f'/studies/{study_id}/protection', headers=auth['viewer']).json()
    assert spent['policy']['spent_epsilon'] == 0.5

    refused = client.post(f'/studies/{study_id}/protected-releases', headers=auth['admin'],
                          json={'name': '超额请求', 'epsilon': 1.0})
    assert refused.status_code == 409 and '余额不足' in refused.json()['detail']

    # Analysts may request a release from the fixed policy; observers may not.
    analyst_release = client.post(f'/studies/{study_id}/protected-releases', headers=auth['analyst'],
                                  json={'name': '分析师受保护发布', 'epsilon': 0.25})
    assert analyst_release.status_code == 200, analyst_release.text
    assert analyst_release.json()['status'] == 'pending'
    assert client.post(f'/studies/{study_id}/protected-releases', headers=auth['viewer'],
                       json={'name': '观察员发起', 'epsilon': 0.1}).status_code == 403
    assert client.post(f'/studies/{study_id}/protection', headers=auth['analyst'],
                       json={'total_epsilon': 1.0}).status_code == 403
