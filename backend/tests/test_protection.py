import threading

import pytest

from src.config.domain import DOMAIN
from src.config.runtime import get_redis, release_artifact
from src.models.observation import Observation
from src.models.protected import ProtectedPolicy, ProtectedRelease
from src.models.study import Study
from src.schemas.protection import ProtectionPolicyInput, ProtectionReleaseInput
from src.services import protection
from src.services import protection as p


class Actor:
    def __init__(self, email='admin@demo.local', role='admin'):
        self.email = email
        self.role = role


ADMIN = Actor()
VIEWER = Actor('viewer@demo.local', 'viewer')
ANALYST = Actor('analyst@demo.local', 'analyst')


def make_study(db, name='青禾·受保护一号', values=None):
    study = Study(name=name, source_filename='protected.csv', description='test')
    db.add(study)
    db.flush()
    for i, value in enumerate(values if values is not None else [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]):
        db.add(Observation(study_id=study.id, source_key=f'P-{i:04d}',
                           values={'moisture': value, 'extract': 30.0 + i}))
    db.commit()
    return study


def make_policy(db, study, total=2.0, bins=None):
    return protection.create_policy(db, study.id,
                                    ProtectionPolicyInput(total_epsilon=total, bins=bins), ADMIN)


def make_release(db, study, name='受保护发布', epsilon=0.5):
    return protection.create_release(db, study.id,
                                     ProtectionReleaseInput(name=name, epsilon=epsilon), ADMIN)


def drain():
    """Run queued protected releases synchronously, like the single worker."""
    from src.config.database import Session
    while True:
        job = get_redis().lpop('protected-queue')
        if not job:
            return
        protection.process_release(int(job), session_factory=Session)


def test_policy_is_fixed_and_budget_refusal(db):
    study = make_study(db)
    make_policy(db, study)
    with pytest.raises(Exception) as conflict:
        protection.create_policy(db, study.id,
                                 ProtectionPolicyInput(total_epsilon=4.0), ADMIN)
    assert getattr(conflict.value, 'status_code', None) == 409

    first = make_release(db, study, epsilon=0.5)
    second = make_release(db, study, epsilon=1.5)
    assert first['status'] == 'pending' and second['status'] == 'pending'
    assert first['id'] != second['id']
    payload = protection.info(db, study.id, ADMIN)['policy']
    assert payload['spent_epsilon'] == 2.0 and payload['remaining_epsilon'] == 0
    with pytest.raises(Exception) as refused:
        make_release(db, study, name='余额不足的新请求', epsilon=1.25)
    assert getattr(refused.value, 'status_code', None) == 409
    assert '余额不足' in refused.value.detail
    assert db.query(ProtectedRelease).count() == 2


def test_ecdf_and_quantiles_come_from_same_nonnegative_counts(db):
    study = make_study(db)
    make_policy(db, study)
    release = make_release(db, study)
    drain()
    row = protection.get_release(db, release['id'], ADMIN)
    result = row['result']
    assert row['status'] == 'available'
    assert len(result['counts']) == len(result['bins'])
    assert all(isinstance(c, int) and c >= 0 for c in result['counts'])
    assert result['noisy_total'] == sum(result['counts'])
    assert result['ecdf'][-1][1] == pytest.approx(1.0)
    # Every ECDF step is exactly the same stored noisy count over the same total.
    cumulative = 0
    for (x0, y0), (x1, y1), count in zip(result['ecdf'], result['ecdf'][1:], result['counts']):
        cumulative += count
        assert y1 == pytest.approx(cumulative / result['noisy_total'])
    # Quantiles are recomputed from the published counts, not from raw values.
    from src.services.protection import _grouped_quantile
    edges = [result['bins'][0]['lower']] + [b['upper'] for b in result['bins']]
    assert result['quantiles']['中位数'] == pytest.approx(
        _grouped_quantile(result['counts'], edges, 0.5))
    assert row['downloadable'] is True
    assert row['archive_checksum'] and release_artifact(row['id']).exists()
    # Quantiles sit inside the fixed bins and are monotone.
    ordered = [result['quantiles'][k] for k in ('P0', 'P25', '中位数', 'P75', 'P100')]
    assert ordered == sorted(ordered)
    assert all(result['bins'][0]['lower'] <= value <= result['bins'][-1]['upper'] for value in ordered)


def test_rename_and_concurrent_retry_reuse_release_without_new_charge(db):
    study = make_study(db)
    make_policy(db, study)
    first = make_release(db, study, name='第一次名称')
    reused = make_release(db, study, name='改名后的重试')
    assert reused['id'] == first['id'] and reused['reused'] is True
    assert reused['name'] == '第一次名称'
    assert protection.info(db, study.id, ADMIN)['policy']['spent_epsilon'] == 0.5

    drain()
    before = protection.get_release(db, first['id'], ADMIN)
    protection.retry(db, first['id'], ADMIN)
    drain()
    after = protection.get_release(db, first['id'], ADMIN)
    assert after['result'] == before['result']
    assert protection.info(db, study.id, ADMIN)['policy']['spent_epsilon'] == 0.5


def test_frozen_input_change_creates_new_release_and_charges_again(db):
    study = make_study(db)
    make_policy(db, study)
    first = make_release(db, study)
    db.add(Observation(study_id=study.id, source_key='P-9999',
                       values={'moisture': 9.0, 'extract': 40.0}))
    db.commit()
    second = make_release(db, study, name='输入已改')
    assert second['id'] != first['id']
    assert protection.info(db, study.id, ADMIN)['policy']['spent_epsilon'] == 1.0
    # The earlier release still generates from its own frozen snapshot.
    drain()
    db.expire_all()
    frozen = protection.get_release(db, first['id'], ADMIN)
    assert frozen['status'] == 'available'
    assert frozen['snapshot_checksum'] != protection.get_release(db, second['id'], ADMIN)['snapshot_checksum']


def test_last_budget_units_concurrent_contention(db):
    study = make_study(db)
    make_policy(db, study, total=1.0)
    study_id = study.id

    def consume(epsilon):
        from src.config.database import Session
        with Session() as session:
            try:
                release = protection.create_release(
                    session, study_id, ProtectionReleaseInput(name='并发请求', epsilon=epsilon), ADMIN)
                return ('ok', release['id'])
            except Exception as error:
                return ('refused', getattr(error, 'detail', str(error)))

    requests = (1.0, 0.75)
    results = []
    threads = [threading.Thread(target=lambda e=e: results.append((e, consume(e)))) for e in requests]
    for thread in threads: thread.start()
    for thread in threads: thread.join()

    grants = [(e, r) for e, r in results if r[0] == 'ok']
    refusals = [(e, r) for e, r in results if r[0] == 'refused']
    # Exactly one of the two competing requests may spend; the loser is told
    # the balance is insufficient and leaves no release row behind.
    assert len(grants) == 1 and len(refusals) == 1, results
    assert '余额不足' in refusals[0][1][1]
    remaining = protection.info(db, study_id, ADMIN)['policy']['remaining_epsilon']
    assert remaining == pytest.approx(1.0 - grants[0][0])
    assert db.query(ProtectedRelease).count() == 1


def test_archive_failure_keeps_charged_result_and_recovers(db, monkeypatch):
    study = make_study(db)
    make_policy(db, study)
    release = make_release(db, study)
    from src.config.database import Session

    def explode(*args, **kwargs):
        raise OSError('disk full')

    with monkeypatch.context() as patch:
        patch.setattr(protection, '_write_archive', explode)
        protection.process_release(release['id'], session_factory=Session)
    failed = protection.get_release(db, release['id'], ADMIN)
    assert failed['status'] == 'pending'
    assert failed['result'] is None
    assert '留档失败' in failed['error']
    assert protection.info(db, study.id, ADMIN)['policy']['spent_epsilon'] == 0.5
    stored = db.get(ProtectedRelease, release['id'])
    original = dict(stored.result)

    drain()  # recovery through the normal worker path
    db.expire_all()
    recovered = protection.get_release(db, release['id'], ADMIN)
    assert recovered['status'] == 'available'
    assert recovered['result'] == original
    assert recovered['downloadable'] is True


def test_release_result_is_hidden_until_available(db, monkeypatch):
    study = make_study(db)
    make_policy(db, study)
    release = make_release(db, study)
    pending = protection.get_release(db, release['id'], ADMIN)
    assert pending['status'] == 'pending' and pending['result'] is None
    with pytest.raises(Exception) as denied:
        protection.export_csv(db, release['id'], VIEWER)
    assert getattr(denied.value, 'status_code', None) == 409
    drain()
    db.expire_all()
    assert protection.export_csv(db, release['id'], VIEWER).strip()


def test_concurrent_identical_requests_share_one_release_and_one_charge(db):
    study = make_study(db)
    make_policy(db, study, total=2.0)
    study_id = study.id
    names = ['并发甲', '并发乙', '并发丙']

    def attempt(name):
        from src.config.database import Session
        with Session() as session:
            try:
                release = protection.create_release(
                    session, study_id, ProtectionReleaseInput(name=name, epsilon=0.5), ADMIN)
                return ('ok', release['id'])
            except Exception as error:  # pragma: no cover - surfaces races
                return ('error', repr(error))

    results = []
    threads = [threading.Thread(target=lambda n=n: results.append(attempt(n))) for n in names]
    for thread in threads: thread.start()
    for thread in threads: thread.join()

    assert all(r[0] == 'ok' for r in results), results
    ids = {r[1] for r in results}
    assert len(ids) == 1
    assert protection.info(db, study_id, ADMIN)['policy']['spent_epsilon'] == 0.5
    assert db.query(ProtectedRelease).count() == 1


def test_generation_failure_keeps_charge_and_blocks_view(db, monkeypatch):
    study = make_study(db)
    make_policy(db, study)
    release = make_release(db, study)
    from src.config.database import Session

    def explode(*args, **kwargs):
        raise ValueError('观测字段不完整')

    with monkeypatch.context() as patch:
        patch.setattr(protection, '_generate', explode)
        protection.process_release(release['id'], session_factory=Session)
    db.expire_all()
    failed = protection.get_release(db, release['id'], ADMIN)
    assert failed['status'] == 'failed'
    assert failed['result'] is None
    assert '观测字段不完整' in failed['error']
    assert failed['downloadable'] is False
    with pytest.raises(Exception) as denied:
        protection.export_csv(db, release['id'], ADMIN)
    assert getattr(denied.value, 'status_code', None) == 409
    assert protection.info(db, study.id, ADMIN)['policy']['spent_epsilon'] == 0.5
    with pytest.raises(Exception) as no_retry:
        protection.retry(db, release['id'], ADMIN)
    assert getattr(no_retry.value, 'status_code', None) == 409
    assert protection.info(db, study.id, ADMIN)['policy']['spent_epsilon'] == 0.5


def test_noise_is_deterministic_from_stored_seed(db, monkeypatch):
    """Even a lost, never-published result is regenerated bit-identically from
    the stored seed; a published result is never redrawn at all."""
    study = make_study(db)
    make_policy(db, study)
    release = make_release(db, study)
    from src.config.database import Session
    from src.services.protection import _generate

    with Session() as session:
        row = session.get(ProtectedRelease, release['id'])
        policy = session.get(ProtectedPolicy, row.policy_id)
        first = _generate(row, policy)
        second = _generate(row, policy)
    assert first['counts'] == second['counts']
    assert first['ecdf'] == second['ecdf']

    drain()
    db.expire_all()
    stored = db.get(ProtectedRelease, release['id'])
    published = dict(stored.result)
    # A retry after an archive failure cannot redraw the published counts.
    protection.retry(db, release['id'], ADMIN)
    drain()
    db.expire_all()
    assert db.get(ProtectedRelease, release['id']).result == published
