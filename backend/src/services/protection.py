"""Protected distribution releases.

A protected release publishes a histogram whose bin counts carry Laplace
noise calibrated to add/remove-one-observation sensitivity (L1 = 1).  The
ECDF and quantiles are derived from that same non-negative noisy histogram,
never from the exact observations.

The privacy budget is a per-batch ledger.  Charging and release insertion
happen in one transaction, using a conditional UPDATE so two requests cannot
spend the last epsilon twice.  The fingerprint covers the frozen input, the
fixed bins and this release's epsilon, so a retry with a different display
name (or a concurrent retry) reuses the stored release and its noise.
"""
import hashlib
import json
import math
import os
import secrets
import time
from bisect import bisect_right

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.config.domain import DOMAIN
from src.config.runtime import get_redis, release_artifact
from src.models.observation import Observation
from src.models.protected import ProtectedPolicy, ProtectedRelease
from src.models.study import Study
from src.services.audits import log
from src.utils.serializers import checksum, now

UNITS = 1_000_000


def settings():
    return DOMAIN.get('protection', {})


def to_units(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError('隐私预算必须为数值')
    if not math.isfinite(number) or number <= 0:
        raise ValueError('隐私预算必须为正的有限数值')
    units = int(round(number * UNITS))
    if units <= 0 or units > 1_000_000_000:
        raise ValueError('隐私预算超出支持范围')
    return units


def from_units(units):
    return units / UNITS


def is_protected(db, study_id):
    return db.scalar(select(ProtectedPolicy.id).where(ProtectedPolicy.study_id == study_id)) is not None


def _study(db, study_id):
    study = db.get(Study, study_id)
    if not study:
        raise HTTPException(404, '业务批次不存在')
    return study


def _raw_rows(db, study_id):
    _study(db, study_id)
    return [{'source_key': x.source_key, 'values': x.values}
            for x in db.scalars(select(Observation).where(Observation.study_id == study_id).order_by(Observation.id))]


def policy_payload(policy):
    return {
        'id': policy.id,
        'study_id': policy.study_id,
        'field': policy.field,
        'bins': policy.bins,
        'total_epsilon': from_units(policy.total_epsilon_units),
        'spent_epsilon': from_units(policy.spent_epsilon_units),
        'remaining_epsilon': from_units(policy.total_epsilon_units - policy.spent_epsilon_units),
        'created_at': policy.created_at,
    }


def info(db, study_id, user=None):
    _study(db, study_id)
    policy = db.scalar(select(ProtectedPolicy).where(ProtectedPolicy.study_id == study_id))
    return {
        'study_id': study_id,
        'protected': policy is not None,
        'policy': policy_payload(policy) if policy else None,
        'releases': list_releases(db, study_id, user),
    }


def _normalise_bins(raw):
    if not isinstance(raw, (list, tuple)) or len(raw) < 2 or len(raw) > 50:
        raise ValueError('分箱必须为至少2个、最多50个递增边界')
    bins = []
    for value in raw:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError('分箱边界必须为数值')
        if not math.isfinite(number) or number < 0 or number > 1e9:
            raise ValueError('分箱边界必须为有限非负数')
        bins.append(number)
    if any(b <= a for a, b in zip(bins, bins[1:])):
        raise ValueError('分箱边界必须严格递增')
    return bins


def create_policy(db, study_id, data, user):
    _study(db, study_id)
    default = settings()
    field = data.field or (default.get('fields') or ['moisture'])[0]
    allowed = default.get('fields') or [f[0] for f in DOMAIN['fields']]
    if field not in allowed:
        raise HTTPException(422, '该指标不开放受保护发布')
    try:
        bins = _normalise_bins(data.bins if data.bins is not None else default.get('bins'))
        total_units = to_units(data.total_epsilon if data.total_epsilon is not None else default.get('total_epsilon'))
    except ValueError as e:
        raise HTTPException(422, str(e))
    existing = db.scalar(select(ProtectedPolicy).where(ProtectedPolicy.study_id == study_id))
    if existing:
        if existing.field == field and existing.bins == bins and existing.total_epsilon_units == total_units:
            return policy_payload(existing)
        raise HTTPException(409, '该批次已固定受保护指标、分箱与总隐私预算，不可修改')
    policy = ProtectedPolicy(study_id=study_id, field=field, bins=bins,
                             total_epsilon_units=total_units, spent_epsilon_units=0, created_at=now())
    db.add(policy)
    log(db, user, 'protection.policy', f'study={study_id} field={field} bins={bins} total={from_units(total_units)}', study_id)
    db.commit()
    return policy_payload(policy)


def _fingerprint(study_id, field, bins, epsilon_units, snapshot_checksum):
    basis = {'study_id': study_id, 'field': field, 'bins': bins,
             'epsilon_units': epsilon_units, 'snapshot_checksum': snapshot_checksum}
    return hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def _enqueue(release_id):
    try:
        get_redis().rpush('protected-queue', int(release_id))
    except Exception:
        # The release stays pending and can be retried; the worker also sweeps
        # pending releases when it starts.
        pass


def _fetch(db, release_id, user):
    release = db.get(ProtectedRelease, release_id)
    if not release:
        raise HTTPException(404, '受保护发布不存在')
    return release_payload(db, release, user)


def release_payload(db, release, user=None, reused=False):
    viewer = user is not None and getattr(user, 'role', None) == 'viewer'
    policy = db.get(ProtectedPolicy, release.policy_id)
    payload = {
        'id': release.id,
        'study_id': release.study_id,
        'name': release.name,
        'status': release.status,
        'epsilon': from_units(release.epsilon_units),
        'field': policy.field if policy else None,
        'bins': policy.bins if policy else None,
        'created_at': release.created_at,
        'generated_at': release.generated_at,
        'available_at': release.available_at,
        'error': release.error,
        'reused': reused,
    }
    if policy:
        # Budget position as recorded at charge time, not "now": later charges
        # must not retroactively change this release's receipt.
        payload['remaining_epsilon_after'] = from_units(release.total_epsilon_units - release.spent_after_units)
        payload['spent_after_epsilon'] = from_units(release.spent_after_units)
        payload['total_epsilon_at_charge'] = from_units(release.total_epsilon_units)
    if not viewer:
        payload.update({
            'policy_id': release.policy_id,
            'fingerprint': release.fingerprint,
            'snapshot': release.snapshot,
            'snapshot_checksum': release.snapshot_checksum,
            'result_checksum': release.result_checksum,
            'archive_checksum': release.archive_checksum,
        })
    # Charging, noisy result and archive must all exist before anything is
    # viewable or downloadable.
    payload['result'] = release.result if release.status == 'available' else None
    payload['downloadable'] = release.status == 'available' and bool(release.archive_checksum)
    return payload


def create_release(db, study_id, data, user):
    _study(db, study_id)
    policy = db.scalar(select(ProtectedPolicy).where(ProtectedPolicy.study_id == study_id))
    if not policy:
        raise HTTPException(409, '该批次尚未由负责人设定受保护分箱与总隐私预算')
    default = settings()
    try:
        epsilon_units = to_units(data.epsilon if data.epsilon is not None else default.get('epsilon_per_release'))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if epsilon_units > policy.total_epsilon_units:
        raise HTTPException(409, '本次隐私预算超过该批次总预算')
    policy_id = policy.id
    policy_field = policy.field
    policy_bins = list(policy.bins)
    policy_total_units = policy.total_epsilon_units
    rows = _raw_rows(db, study_id)
    if not rows:
        raise HTTPException(422, '先录入至少一条业务观测')
    snapshot = [{'source_key': x['source_key'], 'values': x['values']} for x in rows]
    snapshot_checksum = checksum(snapshot)
    fingerprint = _fingerprint(study_id, policy_field, policy_bins, epsilon_units, snapshot_checksum)
    existing = db.scalar(select(ProtectedRelease).where(ProtectedRelease.fingerprint == fingerprint))
    if existing:
        db.rollback()  # release the read snapshot; no budget operation follows
        # A retry may be the only nudge a pending release gets (e.g. the first
        # enqueue was lost).  Re-enqueueing is safe: the worker claims
        # atomically and duplicate queue entries become no-ops.
        if existing.status in ('pending', 'generating'):
            _enqueue(existing.id)
        return release_payload(db, existing, user, reused=True)
    # End the read transaction before the short write transaction.  This keeps
    # SQLite tests from upgrading a stale snapshot and lets the conditional
    # budget UPDATE be the serialisation point in every backend.
    db.rollback()
    release = ProtectedRelease(
        study_id=study_id, policy_id=policy_id, name=data.name,
        epsilon_units=epsilon_units, fingerprint=fingerprint,
        snapshot=snapshot, snapshot_checksum=snapshot_checksum,
        status='pending', result=None, result_checksum='', error='',
        archive_checksum='', created_at=now(), generated_at='', available_at='',
        noise_seed=str(secrets.randbits(63)), spent_after_units=0, total_epsilon_units=policy_total_units,
    )
    db.add(release)
    try:
        db.flush()
        charged = db.execute(
            update(ProtectedPolicy)
            .where(ProtectedPolicy.id == policy_id,
                   ProtectedPolicy.spent_epsilon_units + epsilon_units <= ProtectedPolicy.total_epsilon_units)
            .values(spent_epsilon_units=ProtectedPolicy.spent_epsilon_units + epsilon_units)
        ).rowcount
        if charged != 1:
            db.rollback()
            raise HTTPException(409, '隐私预算余额不足，拒绝生成受保护发布')
        spent_after = db.scalar(select(ProtectedPolicy.spent_epsilon_units).where(ProtectedPolicy.id == policy_id))
        release.spent_after_units = int(spent_after)
        log(db, user, 'protection.release', f'study={study_id} id={release.id} epsilon={from_units(epsilon_units)} spent_after={from_units(spent_after)}', study_id)
        db.commit()
    except IntegrityError:
        # A concurrent identical retry won the unique fingerprint race.  Its
        # release row and charge commit together, because our whole
        # transaction rolls back here.  Under READ COMMITTED the winner may
        # still be committing, so give the row a bounded moment to appear.
        db.rollback()
        for _ in range(50):
            existing = db.scalar(select(ProtectedRelease).where(ProtectedRelease.fingerprint == fingerprint))
            if existing:
                if existing.status in ('pending', 'generating'):
                    _enqueue(existing.id)
                return release_payload(db, existing, user, reused=True)
            db.rollback()
            time.sleep(0.02)
        raise
    _enqueue(release.id)
    return release_payload(db, release, user)


def list_releases(db, study_id, user=None):
    _study(db, study_id)
    return [release_payload(db, x, user) for x in db.scalars(
        select(ProtectedRelease).where(ProtectedRelease.study_id == study_id).order_by(ProtectedRelease.id.desc()))]


def get_release(db, release_id, user=None):
    return _fetch(db, release_id, user)


def retry(db, release_id, user):
    release = db.get(ProtectedRelease, release_id)
    if not release:
        raise HTTPException(404, '受保护发布不存在')
    if release.status == 'available':
        return release_payload(db, release, user)
    if release.status == 'failed':
        raise HTTPException(409, '生成已失败，需重新调整数据后提交新发布')
    _enqueue(release.id)
    log(db, user, 'protection.retry', str(release.id), release.study_id)
    db.commit()
    return release_payload(db, release, user)


def _bins_and_counts(values, edges):
    """Fixed intervals [edges[i], edges[i+1]); len(edges)-1 bins.

    The first and last edges are hard bounds: values outside are clamped so
    every observation still contributes to exactly one public bin.
    """
    counts = [0] * (len(edges) - 1)
    for value in values:
        number = float(value)
        if number <= edges[0]:
            index = 0
        elif number >= edges[-1]:
            index = len(counts) - 1
        else:
            index = max(0, min(bisect_right(edges, number) - 1, len(counts) - 1))
        counts[index] += 1
    return counts


def _interval_rows(edges):
    return [(float(edges[i]), float(edges[i + 1])) for i in range(len(edges) - 1)]


def _grouped_quantile(counts, edges, p):
    total = sum(counts)
    target = p * total
    cumulative = 0
    for i, count in enumerate(counts):
        if count <= 0:
            continue
        lower = float(edges[i])
        upper = float(edges[i + 1])
        if cumulative + count >= target:
            return lower + (target - cumulative) / count * (upper - lower)
        cumulative += count
    return float(edges[-1])


def _summary(counts, edges):
    total = sum(counts)
    if total <= 0:
        raise ValueError('扰动后全部箱计数为0，无法形成分布；本次预算记录保留')
    ecdf = [[float(edges[0]), 0.0]]
    cumulative = 0
    for i, count in enumerate(counts):
        cumulative += count
        ecdf.append([float(edges[i + 1]), cumulative / total])
    quantiles = {label: _grouped_quantile(counts, edges, p)
                 for label, p in [('P0', 0.0), ('P25', .25), ('中位数', .5), ('P75', .75), ('P100', 1.0)]}
    return total, ecdf, quantiles


def _generate(release, policy):
    field = policy.field
    values = []
    for row in release.snapshot:
        value = row.get('values', {}).get(field)
        if value is None:
            raise ValueError('观测字段不完整')
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError('观测字段必须为数值')
        if not math.isfinite(number):
            raise ValueError('观测必须为有限数值')
        values.append(number)
    if not values:
        raise ValueError('空批次无法生成受保护分布')
    edges = [float(x) for x in policy.bins]
    exact = _bins_and_counts(values, edges)
    epsilon = from_units(release.epsilon_units)
    # Add/remove one tea sample changes one bin by 1 => L1 sensitivity 1.
    scale = 1.0 / epsilon
    rng = np.random.default_rng(int(release.noise_seed))
    counts = [max(0, int(round(count + float(rng.laplace(0.0, scale))))) for count in exact]
    total, ecdf, quantiles = _summary(counts, edges)
    intervals = _interval_rows(edges)
    cumulative = 0
    rows = []
    for i, count in enumerate(counts):
        cumulative += count
        rows.append([f'[{intervals[i][0]:g}, {intervals[i][1]:g})', count, round(cumulative / total, 6)])
    field_label = next((f[1] for f in DOMAIN['fields'] if f[0] == field), field)
    return {
        'method': 'bin_histogram_laplace',
        'field': field,
        'field_label': field_label,
        'bins': [{'lower': low, 'upper': high} for low, high in intervals],
        'counts': counts,
        'noisy_total': total,
        'ecdf': ecdf,
        'quantiles': quantiles,
        'epsilon': epsilon,
        'sensitivity': 1,
        'laplace_scale': scale,
        'columns': ['区间', '噪声计数', '累计比例'],
        'rows': rows,
        'table_title': '受保护分箱计数（同一份非负计数推导 ECDF 与分位数）',
        'chart': {'title': '受保护 ECDF · 横条为累计比例', 'points': ecdf},
        'caveat': ('噪声按“增删一份茶样”灵敏度1加拉普拉斯；负计数截为0后，ECDF与分位数均由同一份非负箱计数推导。'
                   '分位数在固定分箱内线性插值，带分组误差；本发布不是单份茶样预测区间。'),
    }


def _write_archive(db, release, policy):
    path = release_artifact(release.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        'release_id': release.id,
        'study_id': release.study_id,
        'name': release.name,
        'status': 'available',
        'field': policy.field,
        'bins': policy.bins,
        'epsilon': from_units(release.epsilon_units),
        'epsilon_units': release.epsilon_units,
        'sensitivity': 1,
        'snapshot_checksum': release.snapshot_checksum,
        'fingerprint': release.fingerprint,
        'result_checksum': release.result_checksum,
        'spent_after_units': release.spent_after_units,
        'total_epsilon_units': release.total_epsilon_units,
        'created_at': release.created_at,
        'generated_at': release.generated_at,
        'result': release.result,
    }
    body = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True)
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(4))
    temporary.write_text(body, encoding='utf-8')
    os.replace(temporary, path)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def process_release(release_id, session_factory=None):
    """Advance one release.  Safe for worker retries; noise is never redrawn
    once stored, and archive failures keep the stored result for recovery."""
    if session_factory is None:
        from src.config.database import Session as session_factory
    with session_factory() as db:
        release = db.get(ProtectedRelease, release_id)
        if not release or release.status in ('available', 'failed'):
            return release.status if release else None
        if release.status == 'pending':
            claimed = db.execute(
                update(ProtectedRelease)
                .where(ProtectedRelease.id == release_id, ProtectedRelease.status == 'pending')
                .values(status='generating')
            ).rowcount
            db.commit()
            if not claimed:
                # Another worker/retry owns this release.  Never draw noise twice.
                db.refresh(release)
                return release.status
            db.refresh(release)
        else:
            # Someone else holds the claim.  Stale claims are reset to pending
            # on worker start, so this is always an active owner.
            return release.status
        policy = db.get(ProtectedPolicy, release.policy_id)
        if not policy:
            release.status = 'failed'
            release.error = '受保护策略不存在'
            db.commit()
            return release.status
        if release.result is None:
            try:
                result = _generate(release, policy)
            except Exception as error:
                release.status = 'failed'
                release.error = str(error)
                log(db, 'system', 'protection.failed', f'{release.id}: {error}', release.study_id)
                db.commit()
                return release.status
            release.result = result
            release.result_checksum = checksum(result)
            release.generated_at = now()
            log(db, 'system', 'protection.generate', release.id, release.study_id)
            db.commit()
        try:
            archive_checksum = _write_archive(db, release, policy)
        except Exception as error:
            # The charge and the noisy result remain in the database.  A retry
            # only rewrites the archive and reuses the same result.
            release.status = 'pending'
            release.error = '留档失败：' + str(error)
            release.available_at = ''
            log(db, 'system', 'protection.archive_failed', f'{release.id}: {error}', release.study_id)
            db.commit()
            return release.status
        release.status = 'available'
        release.archive_checksum = archive_checksum
        release.available_at = now()
        release.error = ''
        log(db, 'system', 'protection.available', release.id, release.study_id)
        db.commit()
        return release.status


def export_csv(db, release_id, user):
    release = db.get(ProtectedRelease, release_id)
    if not release:
        raise HTTPException(404, '受保护发布不存在')
    if release.status != 'available' or release.result is None or not release.archive_checksum:
        raise HTTPException(409, '扣费、扰动结果与留档尚未齐全，暂不可下载')
    policy = db.get(ProtectedPolicy, release.policy_id)
    lines = ['﻿发布编号,指纹,指标,区间下界,区间上界,噪声计数,累计比例,隐私预算epsilon,说明']
    edges = [float(x) for x in policy.bins]
    intervals = _interval_rows(edges)
    cumulative = 0
    total = release.result['noisy_total']
    for i, count in enumerate(release.result['counts']):
        cumulative += count
        lower, upper = intervals[i]
        lines.append(','.join([
            str(release.id), release.fingerprint, policy.field,
            f'{lower:g}', f'{upper:g}', str(count),
            f'{cumulative / total:.6f}', f'{from_units(release.epsilon_units):g}',
            '非负噪声箱计数推导；不得解释为单份茶样预测',
        ]))
    for label, value in release.result['quantiles'].items():
        lines.append(','.join([str(release.id), release.fingerprint, policy.field,
                               '', '', '', f'{value:.6f}',
                               f'{from_units(release.epsilon_units):g}', f'分位数 {label}']))
    log(db, user, 'protection.export', release.id, release.study_id)
    db.commit()
    return '\n'.join(lines) + '\n'
