# -*- coding: utf-8 -*-
"""Площадка отзывает своё согласование из кабинета (владелец 29.09.2026).

Отзыв = запрос аккаунту на переделку баннера по стандартной процедуре: ответ площадки
становится «на доработку» с причиной. Приборы держат последствия по всей системе: пара
выходит из согласованных, получатель откатывается, креатив РК перестаёт быть готовым к
запуску, заведённое в DSP уходит в архив, после старта размещения отозвать нельзя.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.ad.flight import chain_status
from app.launch_prep import revoke as RV
from tests.test_launch_prep_withdraw import env  # noqa: F401 — та же пара «площадка молчит»


def _agree(env):  # noqa: F811
    db = env.db
    env.pair.agreed_at = datetime.utcnow()
    env.target.state = 'согласован'
    db.execute(text("UPDATE launch_prep_review SET verdict = 'ок' WHERE pair_id = :p "
                    "AND kind = 'площадка'"), {'p': env.pair.id})
    db.commit()


def _verdict(db, pair_id):
    return db.execute(text("SELECT verdict, reason, source FROM launch_prep_review "
                           "WHERE pair_id = :p AND kind = 'площадка'"), {'p': pair_id}).first()


def test_revoke_turns_agreed_into_rework_everywhere(env, monkeypatch):  # noqa: F811
    from app.notify import emit as _e  # noqa: F401
    monkeypatch.setattr(RV, "emit", lambda *a, **k: None, raising=False)
    import app.notify as N
    monkeypatch.setattr(N, "emit", lambda *a, **k: None)
    _agree(env)
    out = RV.revoke(env.db, env.pair.id, '  поменять дисклеймер  ', 'Иванов', 'i@x.ru')
    env.db.refresh(env.pair)
    env.db.refresh(env.target)
    v = _verdict(env.db, env.pair.id)
    assert out['verdict'] == 'на доработку'
    assert v.verdict == 'на доработку' and 'поменять дисклеймер' in v.reason and v.source == 'кабинет'
    assert env.pair.agreed_at is None, 'пара осталась согласованной — держит порог ЕРИД'
    assert env.target.state == 'согласование', 'получатель остался «согласован» без пары'
    # Креатив РК: «на доработку» больше не «ждёт запуска» — мяч снова у трафика.
    assert chain_status('ок', v.verdict, has_pair=True) == 'у площадки'
    assert chain_status('ок', 'ок', has_pair=True) == 'ждёт запуска'


def test_dsp_creative_goes_to_archive(env, monkeypatch):  # noqa: F811
    import app.notify as N
    monkeypatch.setattr(N, "emit", lambda *a, **k: None)
    _agree(env)
    env.state.row = SimpleNamespace(id=91, ms_creative_xxhash='ABCDEF0123456789')
    calls = []

    class Ms:
        def creative_set_status(self, xx, st, local_ref=None):
            calls.append((xx, st))
    out = RV.revoke(env.db, env.pair.id, 'другой баннер', 'Иванов', dsp_client=Ms())
    assert calls == [('ABCDEF0123456789', 'ARCHIVE')] and out['dsp']['state'] == 'archived'


@pytest.mark.parametrize('setup,why', [
    (lambda e: None, 'не согласован'),
    (lambda e: (_agree(e), setattr(e.state, 'placement', SimpleNamespace(status='запущен'))), 'запущено'),
    (lambda e: (_agree(e), setattr(e.target, 'state', 'в размещении')), 'запущено'),
])
def test_blockers(env, setup, why):  # noqa: F811
    setup(env)
    env.db.commit()
    with pytest.raises(RV.RevokeError) as e:
        RV.revoke(env.db, env.pair.id, 'причина', 'Иванов')
    assert why in str(e.value)


def test_reason_required(env):  # noqa: F811
    _agree(env)
    with pytest.raises(RV.RevokeError):
        RV.revoke(env.db, env.pair.id, '  ', 'Иванов')


def test_cabinet_view_marks_revocable_and_journal_has_writer():
    from app.cabinet import journal
    from app.database import SessionLocal
    assert 'креатив_отзыв_согласования' in journal.BY_KEY
    db = SessionLocal()
    try:
        d = db.execute(text("SELECT pg_get_viewdef('pub.campaign_creative_v1')")).scalar()
        assert 'revocable' in d and "'ок'" in d and 'withdrawn_at' in d
    finally:
        db.close()
