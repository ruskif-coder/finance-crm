# -*- coding: utf-8 -*-
"""Контур Weborama: имена позиций, сборка тега, клиент на подменном транспорте.

Живьём не проверено ничего: учётных данных ещё нет. Поэтому приборы держат ровно то, что
можно удержать без сети, — правила, из-за которых ошибка будет тихой.
"""
from types import SimpleNamespace

import pytest

from app.weborama import enums, naming
from app.weborama.client import WcmAuthError, WcmClient, WcmError


# ── имена ────────────────────────────────────────────────────────────────────

def test_translit_follows_weborama_table_not_our_matching_one():
    """Таблица Weborama отличается от `reconcile.translit`, и это НЕ дубль по недосмотру.

    Тот огрубляет намеренно ради нечёткого сравнения названий компаний; здесь имя уезжает
    наружу точным идентификатором позиции, по которому вернут пиксель. Прибор фиксирует
    именно расхождение — чтобы «сведение дублей» однажды не склеило их обратно.
    """
    from app.sales.reconcile import translit as matching_translit

    assert naming.translit("Ёжик") == "Yozhik"
    assert naming.translit("хмель") == "khmel"
    assert naming.translit("щавель") == "shchavel"
    assert naming.translit("майка") == "majka"
    # А матчинговый на тех же словах даёт другое — и обязан давать другое.
    assert matching_translit("ёжик") != naming.translit("ёжик").lower()
    assert matching_translit("хмель") != naming.translit("хмель").lower()


def test_translit_keeps_domain_readable_and_drops_the_rest():
    """Шапка шаблона требует латиницу без спецсимволов кроме «_», но домены в собственном
    заполнении владельца идут с точками. Точку и дефис оставляем — без них имя перестаёт
    быть доменом; остальное режем."""
    assert naming.translit("aptechestvo.ru") == "aptechestvo.ru"
    assert naming.translit("аптека-плюс.рф") == "apteka-plyus.rf"
    assert naming.translit("Салвисар 2026!") == "Salvisar_2026"
    assert not naming.has_cyrillic(naming.translit("Сальвисар"))


def test_row_name_matches_the_file_not_the_instruction():
    """Инструкция описывает под именем «Name» ДРУГОЕ поле — то, что в шаблоне собирает
    формула в колонке E. Сверено по файлу владельца: D короче ровно на «аккаунт_формат».
    """
    name = naming.row_name("Desktop", "salvisar", "aptechestvo.ru")
    assert name == "Desktop_salvisar_aptechestvo.ru"
    assert naming.position_name("SIMB-AD", "banner", name) == \
        "SIMB-AD_banner_Desktop_salvisar_aptechestvo.ru"


def test_domain_is_normalised_because_the_tail_url_must_be_bare():
    """Инструкция подчёркивает: адрес в хвосте тега без завершающего слэша. Лишний слэш
    уедет в параметр площадки и склеится со следующим значением."""
    for raw in ("https://Maksavit.ru/", "http://maksavit.ru", "maksavit.ru/catalog?a=1",
                "MAKSAVIT.RU"):
        assert naming.domain_of(raw) == "maksavit.ru"


# ── сборка тега ──────────────────────────────────────────────────────────────

def test_final_tag_substitutes_the_platform_macro():
    """Формулы п. 3.1.2–3.1.3 инструкции, один в один. Разница между Adfox и DSP — только
    в макросе рандомизатора; перепутать значит собрать тег, который не считает показы."""
    pixel = "https://wcm.example.test/px?rnd=[RANDOM]&site="
    dsp = naming.final_tag(pixel, "maksavit.ru", "dsp")
    assert dsp == "https://wcm.example.test/px?rnd={RND}&a.ycp=&site=https://maksavit.ru"
    adfox = naming.final_tag(pixel, "maksavit.ru", "adfox")
    assert "%system.random%&a.ycp=" in adfox
    assert adfox.endswith("https://maksavit.ru")


def test_tag_without_the_placeholder_is_refused_loudly():
    """Пиксель без [RANDOM] — повод остановиться, а не собрать молча: тег без кеш-бастера
    считает показы неверно, и выяснится это по расхождению цифр через месяц."""
    with pytest.raises(ValueError):
        naming.final_tag("https://wcm.example.test/px?site=", "maksavit.ru", "dsp")
    with pytest.raises(ValueError):
        naming.final_tag("px [RANDOM]", "", "dsp")
    with pytest.raises(ValueError):
        naming.final_tag("px [RANDOM]", "maksavit.ru", "неизвестно")


# ── клиент ───────────────────────────────────────────────────────────────────

def _transport(seen, answers):
    def send(method, path, params, data):
        seen.append((method, path, dict(params), dict(data)))
        for key, ans in answers.items():
            if key in path:
                return ans() if callable(ans) else ans
        return {}
    return send


def test_account_id_is_required_and_never_taken_from_the_environment(monkeypatch):
    """Аккаунты Weborama выдаёт списком и закрепляет за клиентами. Взять его из окружения
    значит когда-нибудь записать кампанию одного рекламодателя в измерения другого."""
    monkeypatch.setenv("WEBORAMA_ACCOUNT_ID", "9999")
    with pytest.raises(WcmError):
        WcmClient("")
    assert WcmClient("1234").account_id == "1234"


def test_every_call_carries_both_headers_and_the_account_in_the_body():
    """Заголовков ДВА, и `account_id` дублируется в теле — так в их доке. Забыть второй
    заголовок значит работать не в том аккаунте, а это тихая ошибка."""
    seen = []
    c = WcmClient("1234", email="a@b.c", password="x",
                  transport=_transport(seen, {"jwt_token": {"token": "JWT1"},
                                              "projects": {"id": 1}}))
    c.create_project("Бренд")
    auth = seen[0]
    assert auth[1].endswith("jwt_token/json")
    body = seen[1][3]
    assert body["account_id"] == "1234"
    assert c._headers() == {"X-Weborama-JWTUserAuthToken": "JWT1",
                            "X-Weborama-Account_id": "1234"}


def test_the_id_is_dug_out_of_whatever_shape_comes_back():
    """Урок того же дня на DSP: `Creative.add` отдаёт хеш под ключом `id`, а разбор ждал
    `xxhash` — и успешный вызов считался неудачей, когда объект уже создан. Здесь смотрим
    шире сразу, а не найдя id — говорим, ЧТО пришло."""
    for answer, expect in (({"id": 7}, "7"),
                           ({"project": {"id": "42"}}, "42"),
                           ({"project_id": 5}, "5"),
                           ("77", "77")):
        c = WcmClient("1", email="a@b.c", password="x",
                      transport=_transport([], {"jwt_token": {"token": "J"},
                                                "projects": answer}))
        assert c.create_project("x") == expect

    c = WcmClient("1", email="a@b.c", password="x",
                  transport=_transport([], {"jwt_token": {"token": "J"},
                                            "projects": {"status": "ok"}}))
    with pytest.raises(WcmError) as e:
        c.create_project("x")
    assert "status" in str(e.value), "в отказе должно быть видно, что именно пришло"


def test_only_an_auth_refusal_is_retried_and_only_once():
    """Повтор разрешён ровно на отказ в доступе: только про него известно, что запрос НЕ
    обработан. По таймауту повторять нельзя — создающий вызов мог пройти, и повтор завёл
    бы вторую вставку в чужой системе."""
    calls = {"n": 0}

    def send(method, path, params, data):
        if "jwt_token" in path:
            return {"token": "JWT"}
        calls["n"] += 1
        if calls["n"] == 1:
            raise WcmAuthError("протух")
        return {"id": 1}

    c = WcmClient("1", email="a@b.c", password="x", transport=send)
    assert c.create_project("x") == "1"
    assert calls["n"] == 2, "ровно один повтор"

    def always_auth(method, path, params, data):
        if "jwt_token" in path:
            return {"token": "JWT"}
        raise WcmAuthError("снова")

    with pytest.raises(WcmAuthError):
        WcmClient("1", email="a@b.c", password="x", transport=always_auth).create_project("x")

    def times_out(method, path, params, data):
        if "jwt_token" in path:
            return {"token": "JWT"}
        raise WcmError("таймаут")

    tries = {"n": 0}

    def counting(method, path, params, data):
        if "jwt_token" in path:
            return {"token": "JWT"}
        tries["n"] += 1
        raise WcmError("таймаут")

    with pytest.raises(WcmError):
        WcmClient("1", email="a@b.c", password="x", transport=counting).create_project("x")
    assert tries["n"] == 1, "неизвестный исход не повторяем"


def test_without_credentials_it_says_so_instead_of_calling(monkeypatch):
    """Учётные данные кладёт владелец. Без них — понятный отказ, а не попытка сходить."""
    monkeypatch.delenv("WEBORAMA_EMAIL", raising=False)
    monkeypatch.delenv("WEBORAMA_PASSWORD", raising=False)
    with pytest.raises(WcmAuthError) as e:
        WcmClient("1", transport=lambda *a: {}).login()
    assert "WEBORAMA_EMAIL" in str(e.value)


def test_visibility_format_is_the_default():
    """Видимость и есть причина, по которой верификатор подключают. Формат без неё —
    платить за измерение и не получать измеряемое."""
    assert enums.DEFAULT_DELIVERY_FORMAT == enums.FORMAT_TRACKING_VISIBILITY
    assert enums.DEFAULT_CHANNEL == enums.CHANNEL_DISPLAY

    seen = []
    c = WcmClient("1", email="a@b.c", password="x",
                  transport=_transport(seen, {"jwt_token": {"token": "J"},
                                              "insertions": {"id": 9}}))
    c.create_insertion(campaign_id=17, ad_network_id=112, ad_space_id=1086, label="L")
    body = seen[-1][3]
    assert body["delivery_format_id"] == enums.FORMAT_TRACKING_VISIBILITY
    assert body["ad_space_id"] == 1086


# ── где живут наши размещения ────────────────────────────────────────────────
#
# ⚠ Здесь стоял матчинг наших площадок с их ad_space по домену — и правило «два кандидата
# не выбираем сами» было верным. Задача оказалась выдуманной: первый живой вызов
# 09.09.2026 показал, что каталог ad_space глобальный (1080 записей, французские сайты),
# ни одного нашего домена в нём нет, а ВСЕ наши вставки висят на одном ad_space «SIMB-AD».
# Проверять надо не только как решаем, но и что решаем.

def test_our_ad_space_is_found_by_label_not_by_domain():
    """ad_space и сеть — константы аккаунта. «Какая площадка» несёт только метка вставки."""
    from app.weborama import matching

    payload = {"total_result": "3", "items_per_page": "50", "list": [
        {"id": 1, "label": "Biba", "ad_network_id": 10, "ad_space_type": "Site"},
        {"id": 1080, "label": "SIMB-AD", "ad_network_id": 106, "ad_space_type": "Site"},
        {"id": 5, "label": "Autojournal.Fr", "ad_network_id": 12},
    ]}
    got = matching.find_our_ad_space(payload)
    assert got["id"] == "1080" and got["network"] == 106

    absent = matching.find_our_ad_space({"list": [{"id": 1, "label": "Biba"}]})
    assert absent["id"] is None and "нет ad_space" in absent["reason"]

    twice = matching.find_our_ad_space({"list": [{"id": 1, "label": "SIMB-AD"},
                                                 {"id": 2, "label": "simb-ad"}]})
    assert twice["id"] is None and "2 записей" in twice["reason"]


def test_the_answer_is_paginated_and_we_read_the_total():
    """`items_per_page` по умолчанию 50, а записей 1080. Взять первую страницу и решить,
    что это весь каталог, — самая тихая ошибка здесь."""
    from app.weborama import matching

    payload = {"start_index": "0", "items_per_page": "50", "total_result": "1080",
               "list": [{"id": 7, "label": "x"}]}
    assert matching.total_result(payload) == 1080
    assert len(matching.ad_space_index(payload)) == 1
    assert matching.total_result({"list": []}) is None


def test_ad_space_list_is_read_from_their_wrapper():
    """Их обёртка — ключ `list`. Остальные формы оставлены на случай, если другая ручка
    ответит иначе."""
    from app.weborama import matching

    for payload in ({"list": [{"id": 5, "label": "site"}]},
                    [{"id": 5, "label": "site"}],
                    {"data": [{"ad_space_id": 5, "name": "site"}]}):
        assert matching.ad_space_index(payload)[0]["id"] == "5"


def test_project_label_carries_deal_brand_and_month():
    """Решение владельца 09.09.2026: у них проект зовётся `afalaza_2026`, у нас должен —
    `<сделка>_afalaza_2026-09`. Их имя не отвечает на вопрос, к какой сделке относится
    проект, а в одном месяце сделок одного бренда бывает несколько."""
    from datetime import date

    assert naming.project_label("ZCBPLS", "Афалаза", "2026-09") == "ZCBPLS_afalaza_2026-09"
    # Месяц принимаем и датой — РК хранит его как date, и приводить на каждом вызове
    # значило бы позволить двум местам форматировать по-разному.
    assert naming.project_label("ZCBPLS", "afalaza", date(2026, 9, 1)) == "ZCBPLS_afalaza_2026-09"
    # Бренд в нижнем регистре: так названы ВСЕ кампании в их файле и в кабинете.
    assert naming.project_label("A1", "Viferon", "2026-01") == "A1_viferon_2026-01"


def test_project_label_refuses_incomplete_input():
    """Каждая часть имени несёт смысл: без сделки проект не найти, без бренда он не
    отличается от соседнего, без месяца — от прошлогоднего."""
    for args in (("", "afalaza", "2026-09"),
                 ("ZCBPLS", "", "2026-09"),
                 ("ZCBPLS", "afalaza", "сентябрь"),
                 ("ZCBPLS", "afalaza", "2026-9")):
        with pytest.raises(ValueError):
            naming.project_label(*args)


def test_positions_are_compared_case_insensitively():
    """В их кабинете имена собраны из набранного человеком в Excel: `..._Maksavit.ru` с
    заглавной рядом с `..._minicen.ru` со строчной. Наши домены все строчные (41 из 41),
    поэтому точное сравнение объявило бы уже заведённую позицию новой — а это дубль в
    чужом кабинете либо «пиксель потерялся».
    """
    ours = naming.position_name("SIMB-AD", "banner",
                                naming.row_name("Desktop", "anaferon", "maksavit.ru"))
    theirs = "SIMB-AD_banner_Desktop_anaferon_Maksavit.ru"
    assert ours != theirs, "регистр действительно расходится — на этом и строится прибор"
    assert naming.same_position(ours, theirs)
    assert not naming.same_position(ours, "SIMB-AD_banner_Desktop_anaferon_minicen.ru")


def test_campaign_label_is_brand_plus_id():
    """У них кампания зовётся просто `anaferon`, и в списке из 25 таких строк не понять,
    к чему относится каждая. ID делает её самоопознаваемой на обзорном экране, где проект
    не виден."""
    assert naming.campaign_label("Афалаза", "ZCBPLS") == "afalaza_ZCBPLS"
    assert naming.campaign_label("anaferon", 2491) == "anaferon_2491"
    for args in (("", "ZCBPLS"), ("afalaza", ""), ("afalaza", None)):
        with pytest.raises(ValueError):
            naming.campaign_label(*args)


def test_the_whole_naming_canon_holds_together():
    """Четыре имени одной РК рядом — так видно, что они не спорят друг с другом и что
    вставка остаётся уникальной в пределах кампании."""
    from datetime import date

    proj = naming.project_label("ZCBPLS", "Афалаза", date(2026, 9, 1))
    camp = naming.campaign_label("Афалаза", "ZCBPLS")
    name = naming.row_name("Desktop", camp, "003ms.ru")
    pos = naming.position_name("SIMB-AD", "banner", name)
    assert proj == "ZCBPLS_afalaza_2026-09"
    assert camp == "afalaza_ZCBPLS"
    assert pos == "SIMB-AD_banner_Desktop_afalaza_ZCBPLS_003ms.ru"
    # Разные площадки — разные позиции; это и есть требование уникальности в шаблоне.
    other = naming.position_name("SIMB-AD", "banner",
                                 naming.row_name("Desktop", camp, "maksavit.ru"))
    assert not naming.same_position(pos, other)


# ── экран стенда ─────────────────────────────────────────────────────────────

def test_stand_refuses_without_credentials_and_without_account(monkeypatch):
    """Две разные причины отказа, и человек должен видеть, которая из них.

    Аккаунт вводится НА ЭКРАНЕ: Weborama выдаёт их списком и закрепляет за клиентами, и
    молчаливое умолчание из окружения однажды запишет кампанию одного рекламодателя в
    измерения другого. Переменная только подставляет значение в поле.
    """
    from fastapi import HTTPException
    from app.routers import weborama_demo as W

    monkeypatch.setenv("WEBORAMA_EMAIL", "a@b.c")
    monkeypatch.setenv("WEBORAMA_PASSWORD", "x")
    with pytest.raises(HTTPException) as e:
        W._client("")
    assert e.value.status_code == 400 and "аккаунт" in str(e.value.detail).lower()

    monkeypatch.delenv("WEBORAMA_PASSWORD", raising=False)
    with pytest.raises(HTTPException) as e2:
        W._client("10419")
    assert "WEBORAMA_PASSWORD" in str(e2.value.detail)


def test_the_token_never_reaches_the_screen():
    """Экран видят несколько человек, а JWT — ключ ко всему аккаунту. Наружу уходит только
    факт входа и длина: этого хватает, чтобы отличить «вошли» от «пришло не то»."""
    import inspect
    from app.routers import weborama_demo as W

    src = inspect.getsource(W.login)
    assert '"token_length"' in src
    assert '"token"' not in src.replace('"token_length"', '')


def test_delivery_format_defaults_to_visibility_but_is_choosable():
    """Формат решает, ЧЕМ вставка меряет, и это выбор, а не константа.

    Замерено 09.09.2026: формат 4 отдаёт js-блок (видимость картинкой 1×1 не измерить),
    формат 3 — пиксель `a.A=im`. В DSP это разные поля: `js_code_audit` и `pixel`.
    По умолчанию 4 — ради видимости верификатор и подключают.
    """
    from app.routers import weborama_demo as W

    assert enums.DEFAULT_DELIVERY_FORMAT == enums.FORMAT_TRACKING_VISIBILITY
    assert W.InsertionIn(account_id="1", campaign_id="1", ad_network_id="106",
                         ad_space_id="1080", campaign_label="c",
                         domain="a.ru").delivery_format_id == enums.FORMAT_TRACKING_VISIBILITY
    assert W.InsertionIn(account_id="1", campaign_id="1", ad_network_id="106",
                         ad_space_id="1080", campaign_label="c", domain="a.ru",
                         delivery_format_id=3).delivery_format_id == enums.FORMAT_TRACKING_PIXEL


def test_every_step_is_written_to_a_readable_journal(tmp_path, monkeypatch):
    """Разбирать проблемы обмена по пересказу невозможно — нужен сырой ответ целиком.
    Схему хранения согласуют до кода, поэтому журнал пока файл; он смонтирован наружу.

    Пароль и токен в него не попадают: в шаге входа пишется аккаунт и длина токена.
    """
    from app.routers import weborama_demo as W

    path = tmp_path / "wcm.log"
    monkeypatch.setattr(W, "LOG_PATH", str(path))
    W._journal("1 · вход", SimpleNamespace(name="Тест", id=1),
               {"account_id": "10419"}, {"ok": True, "token_length": 860})
    W._journal("7 · вставка", SimpleNamespace(name="Тест", id=1),
               {"domain": "maksavit.ru"}, error="Weborama отказала")
    text = path.read_text(encoding="utf-8")
    assert "1 · вход" in text and "7 · вставка" in text
    assert "860" in text and "ОТКАЗ" in text
    assert "password" not in text.lower()

    # Сбой записи не роняет шаг: журнал — свидетель, а не участник.
    monkeypatch.setattr(W, "LOG_PATH", "/нет/такого/пути/x.log")
    W._journal("шаг", SimpleNamespace(name="Т", id=1), {"a": 1})


def test_landing_url_is_checked_before_sending():
    """09.09.2026 в это поле уехала markdown-ссылка целиком —
    `[www.simb-ad.com](https://www.simb-ad.com)`, — и Weborama ответила 406, вернув весь
    объект с умолчаниями вместо объяснения. Сказать «это не адрес» можно раньше и яснее.
    """
    from fastapi import HTTPException
    from app.routers import weborama_demo as W

    bad = ["[www.simb-ad.com](https://www.simb-ad.com)", "www.simb-ad.com",
           "https://a b.ru", "simb-ad.com", ""]
    for u in bad:
        with pytest.raises(HTTPException) as e:
            W.create_campaign(W.CampaignIn(account_id="1", project_id="1", brand="b",
                                           ident="X", landing_url=u), None, None)
        assert e.value.status_code == 400


def test_their_refusal_is_not_cut_off_before_the_reason():
    """300 символов не хватало: на 406 они возвращают ВЕСЬ объект с умолчаниями, и причина
    оказывается за обрезом. Сообщение о неудаче не должно прятать её причину — та же
    ошибка, что была с загрузчиком архива в DSP."""
    from app.weborama.client import _refusal

    body = '{"error":{"message":"landing_url is invalid","landing_url":"[a](b)"}}'
    out = _refusal(body)
    assert out.startswith("landing_url is invalid")
    assert "тело:" in out

    long_echo = '{"error":{' + ','.join(f'"f{i}":"{i}"' for i in range(200)) + '}}'
    assert len(_refusal(long_echo)) > 300
    assert _refusal("не json") == "не json"


def test_insertion_without_a_domain_is_refused():
    """ad_space у нас ОДИН на все размещения, поэтому «какая площадка» несёт только метка
    вставки. Поймано на живой пробе 09.09.2026: вставка уехала с меткой
    `SIMB-AD_banner_Desktop_viferon_F99A73` — без сайта, то есть неотличимой от следующей
    такой же. Показы двух сайтов слились бы в одну строку отчёта.
    """
    from fastapi import HTTPException
    from app.routers import weborama_demo as W

    for bad in ("", "   ", None):
        with pytest.raises(HTTPException) as e:
            W.create_insertion(W.InsertionIn(
                account_id="1", campaign_id="29", ad_network_id="106", ad_space_id="1080",
                campaign_label="viferon_F99A73", domain=bad or ""), None, None)
        assert e.value.status_code == 400 and "домен" in str(e.value.detail).lower()


# ── разбор тега: показ против клика ──────────────────────────────────────────
#
# Живая проба 09.09.2026. Ответ `insertions/{id}/tags.json` — массив, и в нём не «пиксель»,
# а js-блок, внутри которого ДВЕ разные ссылки. Экран искал «любой адрес с [RANDOM]» и
# подставил КЛИКОВЫЙ счётчик на место показного пикселя: тег собрался, уехал бы в DSP, всё
# «работает», показы не считаются — видно через месяц по пустым отчётам.

REAL_TAG = [{
    "tracking_id": "567", "ad_space_id": 1080, "placement_id": 0, "campaign_id": 29,
    "js_ru": ('<script type="text/javascript">\n'
              "var adperfobj = {\n   account_id : 10419\n  ,tracking_element_id : 567\n"
              "  ,width : ~WIDTH~\n  ,height : ~HEIGHT~\n"
              "  ,fullhost : 'wcm.weborama-tech.ru'\n  ,random : '[RANDOM]'\n};\n"
              "document.write('<scr'+'ipt src=\"https://cstatic-ru-cv.weborama-tech.ru/"
              "public/js/advertiserv2/ru/adperf_launch_1.0.0_scrambled.js\"></scr'+'ipt>');\n"
              "</script>\n\n"
              '<a href="https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=cl&'
              'a.si=10419&a.te=567&g.ism=0&erid=[ERID_ID]&er=[ERID_VALUE]&a.ra=[RANDOM]&'
              'g.lu="></a>'),
}]


def test_click_tracker_is_never_taken_for_an_impression_pixel():
    """Разбираем по `a.A`, а не по виду строки: обе ссылки выглядят одинаково и обе
    содержат [RANDOM]."""
    from app.weborama import tags

    p = tags.parse(REAL_TAG)
    assert p["click"] and "a.A=cl" in p["click"]
    assert p["impression"] is None, "в этом ответе показного пикселя НЕТ"
    assert tags.impression_pixel(REAL_TAG) is None
    assert p["tracking_id"] == "567" and p["campaign_id"] == 29
    # Плейсхолдеры видны все — по ним понятно, что подставляется на нашей стороне.
    assert set(p["placeholders"]) >= {"[RANDOM]", "[ERID_ID]", "[ERID_VALUE]", "~WIDTH~"}
    # Адрес их лаунчера не должен считаться ни пикселем, ни кликом.
    assert any("adperf_launch" in u for u in p["others"])


def test_impression_pixel_is_picked_when_it_is_there():
    """Когда показной приходит — берём именно его, а не первый попавшийся."""
    from app.weborama import tags

    payload = [{"tracking_id": "546", "js_ru":
                '<img src="https://wcm.example.test/d.fcgi?a.A=im&a.te=546&a.ra=[RANDOM]">'
                '<a href="https://wcm.example.test/d.fcgi?a.A=cl&a.te=546"></a>'}]
    got = tags.impression_pixel(payload)
    assert got and "a.A=im" in got and "a.A=cl" not in got


def test_assembling_from_a_click_tracker_is_refused():
    """Последний рубеж: даже если кликовый попал в поле руками, собрать из него «пиксель»
    нельзя."""
    from fastapi import HTTPException
    from app.routers import weborama_demo as W

    click = ("https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=cl&a.si=10419&"
             "a.te=567&a.ra=[RANDOM]")
    with pytest.raises(HTTPException) as e:
        W.assemble(W.AssembleIn(pixel=click, domain="maksavit.ru", kind="dsp"), None)
    assert e.value.status_code == 400 and "клик" in str(e.value.detail).lower()


REAL_TAG_F3 = [{
    "tracking_id": "570", "ad_space_id": 1080, "placement_id": 0, "campaign_id": 32,
    "image-ssl_ru": ('<a href="https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=cl&'
                     'a.si=10419&a.te=570&gdpr=${GDPR}&gdpr_consent=${GDPR_CONSENT_284}&'
                     'erid=[ERID_ID]&er=[ERID_VALUE]&a.ra=[RANDOM]&g.lu=" target="_blank">'
                     '<img src="https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=im&'
                     'a.si=10419&a.te=570&a.he=~HEIGHT~&a.wi=~WIDTH~&a.hr=p&gdpr=${GDPR}&'
                     'gdpr_consent=${GDPR_CONSENT_284}&a.ra=[RANDOM]" width="~WIDTH~" '
                     'height="~HEIGHT~" style="border:0px"></a>'),
    "amp": ('<amp-pixel src="https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?a.A=im&'
            'a.si=10419&a.te=570&a.he=~HEIGHT~&a.wi=~WIDTH~&a.hr=p&a.ra=RANDOM">'
            '</amp-pixel>'),
}]


def test_format_three_gives_the_impression_pixel_format_four_does_not():
    """Замерено 09.09.2026 на живых вставках. Формат 4 меряет ВИДИМОСТЬ, а её картинкой
    1×1 не измерить — отсюда js-блок без показного пикселя. Формат 3 отдаёт `image-ssl_ru`
    и `amp`, и в них показной есть. Это не сбой, а разные инструменты."""
    from app.weborama import tags

    assert tags.impression_pixel(REAL_TAG) is None          # формат 4
    px = tags.impression_pixel(REAL_TAG_F3)                 # формат 3
    assert px and "a.A=im" in px and "a.te=570" in px


def test_tracking_id_is_not_the_insertion_id():
    """ЛОВУШКА. У вставок 567–569 `a.te` совпадал с их id, и это выглядело правилом.
    Вставка 571 вернула `tracking_id` 570, а вставки 570 не существует вовсе (их API на
    неё отвечает 500). Значит `a.te` — id ОТСЛЕЖИВАЮЩЕГО ЭЛЕМЕНТА, своя последовательность.

    Отсюда правило: пиксель НИКОГДА не собираем из наших id — только забираем тегом.
    Собранный «по образцу» пиксель считал бы показы чужой площадки.
    """
    from app.weborama import tags

    p = tags.parse(REAL_TAG_F3)
    assert p["tracking_id"] == "570"
    assert "a.te=570" in p["impression"]
    # id вставки (571) в ответе не встречается вовсе — сверять их бессмысленно.
    assert "571" not in str(REAL_TAG_F3)


def test_leftover_macros_are_reported_and_size_can_be_filled():
    """Пиксель формата 3 приходит с `~WIDTH~`, `~HEIGHT~` и `${GDPR}`. DSP таких макросов
    не знает: строка уедет как есть, и в счётчик попадёт мусор вместо размера. В выгрузке
    Excel их не было — там уже стояли `a.he=1&a.wi=1`."""
    from app.weborama import naming, tags

    px = tags.impression_pixel(REAL_TAG_F3)
    tag = naming.final_tag(px, "maksavit.ru", "dsp")
    rest = tags.leftovers(tag)
    assert "~WIDTH~" in rest and "~HEIGHT~" in rest and "${GDPR}" in rest

    # Размер мы ЗНАЕМ — он объявлен в самом баннере, выдумывать ничего не нужно.
    filled = naming.final_tag(tags.fill_size(px, 240, 400), "maksavit.ru", "dsp")
    rest2 = tags.leftovers(filled)
    assert "~WIDTH~" not in rest2 and "a.wi=240" in filled and "a.he=400" in filled
    # ${GDPR} остаётся — это вопрос к Weborama, а не то, что мы вправе подставить сами.
    assert "${GDPR}" in rest2


# ── схема контура (миграция 2026-09-09_weborama.sql) ─────────────────────────

def test_one_entity_is_registered_in_wcm_exactly_once():
    """ГЛАВНОЕ ограничение схемы, и оно в БАЗЕ, а не в коде.

    У Weborama нет идемпотентности: повтор заведёт вторую вставку, а удалить или
    переименовать её по API нечем — два счётчика поделят показы одной площадки, и оба
    числа будут неверны. Проверка в коде не спасает от двух одновременных нажатий,
    ограничение спасает.
    """
    from sqlalchemy.exc import IntegrityError

    from app.database import SessionLocal
    from app.weborama.models import KIND_INSERTION, WeboramaRef

    db = SessionLocal()
    try:
        base = dict(account_id="TESTACC", kind=KIND_INSERTION, local_id=999001)
        db.add(WeboramaRef(**base, wcm_id="1", label="ТЕСТ · первая"))
        db.commit()
        db.add(WeboramaRef(**base, wcm_id="2", label="ТЕСТ · вторая"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Тот же наш объект в ДРУГОМ аккаунте — законная вторая запись: аккаунты
        # закреплены за клиентами, и это разные измерения.
        db.add(WeboramaRef(**{**base, "account_id": "TESTACC2"},
                           wcm_id="3", label="ТЕСТ · другой аккаунт"))
        db.commit()
        assert db.query(WeboramaRef).filter(WeboramaRef.local_id == 999001).count() == 2
    finally:
        db.query(WeboramaRef).filter(WeboramaRef.local_id == 999001).delete()
        db.commit()
        db.close()


def test_an_unfinished_attempt_is_visible_as_unknown():
    """`finished_at IS NULL` = вызов ушёл, ответ не вернулся. Такую попытку не повторяют
    автоматически: объект в чужой системе мог создаться. Под этот поиск заведён отдельный
    частичный индекс — незавершённые ищут всегда все сразу."""
    from app.database import SessionLocal
    from app.weborama.models import KIND_PROJECT, WeboramaSubmission

    db = SessionLocal()
    try:
        s = WeboramaSubmission(account_id="TESTACC", kind=KIND_PROJECT, local_id=999002,
                               method="/advertiser/projects.json",
                               request={"label": "ТЕСТ"})
        db.add(s); db.commit()
        assert s.started_at is not None and s.finished_at is None
        open_now = (db.query(WeboramaSubmission)
                    .filter(WeboramaSubmission.finished_at.is_(None),
                            WeboramaSubmission.local_id == 999002).count())
        assert open_now == 1
    finally:
        db.query(WeboramaSubmission).filter(WeboramaSubmission.local_id == 999002).delete()
        db.commit()
        db.close()


def test_dsp_hashes_are_not_duplicated_into_the_weborama_contour():
    """Хеши DSP уже живут в РК и в креативах и уже показываются в кабинете трафика.
    Второе хранилище того же факта разошлось бы с первым — поэтому в контуре Weborama их
    нет, и колонка DSP на экране считается из существующих полей."""
    from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
    from app.weborama.models import WeboramaRef, WeboramaSubmission

    assert hasattr(AdCampaign, "ms_campaign_xxhash")
    assert hasattr(AdCampaignCreative, "ms_creative_xxhash")
    assert hasattr(AdCampaignPlacement, "weborama_pixel")
    for m in (WeboramaRef, WeboramaSubmission):
        names = {c.name for c in m.__table__.columns}
        assert not [n for n in names if "xxhash" in n or n.startswith("ms_")]
