"""Test-only fixture and unthrottled HTTP burst. No product auth overrides."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
import re
import secrets
import time
import traceback
from uuid import uuid4

import asyncpg
from sqlalchemy.engine import make_url


def emit(value):
    print(json.dumps(value), flush=True)


def percentiles(values):
    ordered = sorted(values)
    return {name: round(ordered[min(len(ordered)-1, math.ceil(len(ordered)*q)-1)], 3)
            for name, q in [('p50', .5), ('p95', .95), ('p99', .99), ('max', 1)]} if ordered else {}


async def request(path, token=None, payload=None, timeout=180):
    writer = None
    try:
        async with asyncio.timeout(timeout):
            reader, writer = await asyncio.open_connection('backend', 8000)
            data = json.dumps(payload).encode() if payload is not None else b''
            headers = [f'{"POST" if payload is not None else "GET"} {path} HTTP/1.1',
                       'Host: backend:8000', 'Connection: close', 'Origin: http://localhost:5173',
                       'Content-Type: application/json', f'Content-Length: {len(data)}']
            if token:
                headers.append('Cookie: creativeops_session=' + token)
            writer.write(('\r\n'.join(headers) + '\r\n\r\n').encode() + data)
            await writer.drain()
            raw = await reader.readuntil(b'\r\n\r\n')
            code = int(raw.split(b' ', 2)[1])
            body = await reader.read()
            # Uvicorn may stream chunked responses through middleware.
            if b'transfer-encoding: chunked' in raw.lower():
                chunks = []
                while body:
                    size, body = body.split(b'\r\n', 1)
                    n = int(size.split(b';')[0], 16)
                    if n == 0:
                        break
                    chunks.append(body[:n])
                    body = body[n+2:]
                body = b''.join(chunks)
            return code, body
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()


async def snapshot(db):
    states = {row['state']: row['n'] for row in await db.fetch('SELECT state::text,count(*) n FROM jobs GROUP BY state')}
    outbox = {row['status']: row['n'] for row in await db.fetch('SELECT status::text,count(*) n FROM outbox_events GROUP BY status')}
    return dict(states=states, outbox=outbox,
                db_connections=await db.fetchval('SELECT count(*) FROM pg_stat_activity'),
                held_reservations=await db.fetchval("SELECT count(*) FROM credit_reservations WHERE status='held'"))


async def run(args):
    from app.config import get_settings
    settings = get_settings()
    url = make_url(settings.database_url)
    if (not re.fullmatch(r'ownership-verify-[0-9a-f]{12}', args.project)
            or url.host != 'db' or url.database != args.project.replace('-', '_')
            or settings.ai_provider != 'mock' or settings.app_env != 'local'
            or settings.auth_google_client_id or settings.auth_google_client_secret.get_secret_value()
            or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')):
        raise ValueError('load_target_refused')
    code, body = await request('/api/health')
    assert code == 200 and json.loads(body)['vertex']['status'] == 'mock_provider'
    db = await asyncpg.connect(host='db', user=url.username, password=url.password, database=url.database)
    try:
        for table in ('users', 'jobs', 'user_sessions', 'outbox_events', 'assets'):
            assert await db.fetchval('SELECT count(*) FROM ' + table) == 0, 'nonempty_target'
        tokens = [secrets.token_urlsafe(32) for _ in range(args.count)]
        users = [uuid4() for _ in tokens]
        now = datetime.now(timezone.utc)
        async with db.transaction():
            await db.executemany("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,$2,$3,true,'user','active','oauth',$4,$4)",
                [(uid, 'load-'+str(i), f'load-{i}@example.invalid', now-timedelta(hours=1)) for i, uid in enumerate(users)])
            await db.executemany('INSERT INTO user_sessions(id,user_id,token_hash,created_at,last_seen_at,absolute_expires_at) '
                'VALUES($1,$2,$3,$4,$4,$5)',
                [(uuid4(), uid, hashlib.sha256(token.encode()).digest(), now, now+timedelta(days=7)) for uid, token in zip(users,tokens)])
        emit({'seeded_users': args.count})
        gate = asyncio.Event()
        active = peak = 0
        starts, durations, codes, errors, accepted = [], [], Counter(), Counter(), {}
        started = time.monotonic()

        async def submit(index):
            nonlocal active, peak
            await gate.wait()
            t = time.monotonic()
            starts.append(t-started)
            active += 1
            peak = max(peak, active)
            try:
                code, body = await request('/api/generations', tokens[index], {
                    'mode': 't2i', 'model': 'imagen-4.0-fast-generate-001',
                    'prompt': 'mock load fixture '+str(index), 'number_of_images': 1,
                    'aspect_ratio': '1:1'}, timeout=args.request_timeout)
                codes[str(code)] += 1
                if code == 201:
                    accepted[json.loads(body)['id']] = index
            except Exception as error:
                errors[type(error).__name__] += 1
            finally:
                durations.append(time.monotonic()-t)
                active -= 1

        tasks = [asyncio.create_task(submit(i)) for i in range(args.count)]
        await asyncio.sleep(0)  # Schedule every task at the barrier before release.
        started = time.monotonic()
        gate.set()
        all_requests = asyncio.gather(*tasks)
        samples = []
        while not all_requests.done():
            await asyncio.wait([all_requests], timeout=5)
            sample = {'elapsed': round(time.monotonic()-started, 3), 'active_http': active,
                      'responses': sum(codes.values()), **await snapshot(db)}
            samples.append(sample)
            emit({'sample': sample})
        await all_requests
        submit_seconds = time.monotonic()-started
        emit({'submission': dict(statuses=codes, errors=errors, peak=peak, launch_spread=max(starts)-min(starts))})
        deadline = time.monotonic()+args.drain_seconds
        while True:
            state = await snapshot(db)
            nonterminal = sum(n for k,n in state['states'].items() if k not in ('completed','failed','cancelled'))
            if not nonterminal or time.monotonic() >= deadline:
                break
            await asyncio.sleep(min(10, max(0, deadline-time.monotonic())))
            sample = {'elapsed': round(time.monotonic()-started, 3), **await snapshot(db)}
            samples.append(sample)
            emit({'sample': sample})
        final = await snapshot(db)
        checks = {
            'jobs': await db.fetchval('SELECT count(*) FROM jobs'),
            'distinct_owners': await db.fetchval('SELECT count(DISTINCT owner_user_id) FROM jobs'),
            'assets': await db.fetchval('SELECT count(*) FROM assets'),
            'usage_records': await db.fetchval('SELECT count(*) FROM credit_usage_records'),
            'reserved_microcredits': int(await db.fetchval('SELECT coalesce(sum(reserved_microcredits),0) FROM credit_grants')),
            'completed_without_one_asset': await db.fetchval("SELECT count(*) FROM jobs j WHERE state='completed' AND (SELECT count(*) FROM assets a WHERE a.job_id=j.id)<>1"),
        }
        completion = [float(row['seconds']) for row in await db.fetch("SELECT extract(epoch FROM updated_at-created_at) seconds FROM jobs WHERE state='completed'")]
        # Read through the authenticated public file route, not a fake asset stub.
        file_checks = file_bytes = 0
        rows = await db.fetch("SELECT j.id,a.local_path FROM jobs j JOIN assets a ON a.job_id=j.id WHERE j.state='completed' ORDER BY j.id LIMIT 20")
        for row in rows:
            index = accepted.get(str(row['id']))
            if index is None:
                continue
            path = '/files/' + str(row['id']) + '/output.png'
            code, data = await request(path, tokens[index])
            if code == 200 and data.startswith(b'\x89PNG\r\n\x1a\n'):
                file_checks += 1
                file_bytes += len(data)
        passed = (codes == {'201': args.count} and not errors and peak == args.count
                  and final['states'] == {'completed': args.count}
                  and checks['jobs'] == checks['distinct_owners'] == checks['assets'] == checks['usage_records'] == args.count
                  and final['held_reservations'] == checks['reserved_microcredits'] == checks['completed_without_one_asset'] == 0
                  and file_checks == min(args.count,20))
        emit({'result': dict(complete=True, passed=passed, statuses=dict(codes), errors=dict(errors),
              accepted=len(accepted), peak_inflight=peak, launch_spread_seconds=round(max(starts)-min(starts),3),
              submission_seconds=round(submit_seconds,3), request_latency_seconds=percentiles(durations),
              completion_latency_seconds=percentiles(completion), total_seconds=round(time.monotonic()-started,3),
              final=final, checks=checks, file_samples_passed=file_checks, file_sample_bytes=file_bytes,
              retries=0, peak_db_connections=max(s['db_connections'] for s in samples))})
    finally:
        await db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--drain-seconds', type=int, required=True)
    parser.add_argument('--request-timeout', type=int, required=True)
    options = parser.parse_args()
    assert 1 <= options.count <= 10000
    try:
        asyncio.run(run(options))
    except Exception as error:
        emit({'failure': type(error).__name__, 'frames': [
            {'file': frame.filename.rsplit('/', 1)[-1], 'line': frame.lineno}
            for frame in traceback.extract_tb(error.__traceback__)[-4:]]})
        raise SystemExit(2)
