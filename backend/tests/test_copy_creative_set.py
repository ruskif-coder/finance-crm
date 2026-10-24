"""«Скопировать креатив» (владелец 24.10.2026): копия настроек для ускорения заведения.

Переносится состав площадок с их ссылками — в том числе присланными площадкой по
копируемому креативу. Не переносится то, что принадлежит самому материалу и его пути:
файл, письмо о правах, первичная проверка, ЕРИД, отправка. Объём показов не переносится —
сумма объёмов по креативам РК ограничена планом, копия съела бы его дважды.
"""
from app.models import AuditLog
from app.launch_prep.models import LaunchPrepCreativeFile, LaunchPrepCreativeSet, LaunchPrepSetTarget
from app.routers import launch_prep as lp
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401


def _members(db, set_id):
    return {m.target_id: m for m in db.query(LaunchPrepSetTarget).filter(LaunchPrepSetTarget.set_id == set_id)}


def _drop_audit(db, deal_id):
    db.query(AuditLog).filter(AuditLog.action == "copy_creative_set",
                              AuditLog.entity_id == deal_id).delete(synchronize_session=False)
    db.commit()


def test_copy_carries_targets_and_links_but_not_the_material(env):  # noqa: F811
    src = env.cset
    src.title, src.description, src.erid = "Баннер осень", "описание для ОРД", "TESTERID"
    src.report_group = "Аудитория А"
    t0, t1 = env.targets
    m = _members(env.db, src.id)
    m[t0.id].deeplink_url = "https://app.test/deep"     # ссылка, присланная площадкой
    m[t1.id].plan_show = 1000
    env.db.commit()
    try:
        out = lp.copy_set(src.id, env.db, _ADMIN)
        new = env.db.get(LaunchPrepCreativeSet, out["id"])
        assert new.no > src.no and new.deal_id == src.deal_id
        assert new.origin == "параллельный"
        assert new.title == "Баннер осень (копия)"
        assert new.description == "описание для ОРД"
        assert new.report_group == "Аудитория А", "копия — та же аудитория"
        assert new.erid is None and new.sent_at is None and new.rights_letter_path is None
        assert env.db.query(LaunchPrepCreativeFile).filter(LaunchPrepCreativeFile.set_id == new.id).count() == 0

        got = _members(env.db, new.id)
        assert set(got) == {t0.id, t1.id}
        assert got[t0.id].advertiser_url == "https://site.test/tovar/1"
        assert got[t0.id].deeplink_url == "https://app.test/deep"
        assert got[t1.id].plan_show is None, "объём показов не копируется — план РК съелся бы дважды"

        tree = lp.deal_creatives(env.deal.id, env.db, _ADMIN)
        s = next(x for x in tree["sets"] if x["id"] == new.id)
        assert not s["primary_review"], "первичная проверка — у нового файла, её не переносим"
    finally:
        _drop_audit(env.db, env.deal.id)


def test_copy_of_unknown_set_is_404(env):  # noqa: F811
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        lp.copy_set(10 ** 9, env.db, _ADMIN)
    assert e.value.status_code == 404
