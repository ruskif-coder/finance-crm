# -*- coding: utf-8 -*-
"""Числовые справочники WCM. Держим их именами, а не цифрами в коде вызова:
`delivery_format_id=4` в теле запроса ничего не говорит, а `TRACKING_VISIBILITY` говорит.
"""

# Тип кампании (`channel_id`). Наш случай — медийка.
CHANNEL_DISPLAY = 1
CHANNEL_SEARCH = 2
CHANNEL_AFFILIATE = 3
CHANNEL_DIRECT_MARKETING = 4
CHANNEL_SELF_PROMOTION = 5
CHANNEL_SOCIAL = 6

CHANNELS = {
    CHANNEL_DISPLAY: "Display",
    CHANNEL_SEARCH: "Search",
    CHANNEL_AFFILIATE: "Affiliate",
    CHANNEL_DIRECT_MARKETING: "Direct Marketing",
    CHANNEL_SELF_PROMOTION: "Self Promotion",
    CHANNEL_SOCIAL: "Social",
}

# Тип вставки (`delivery_format_id`).
FORMAT_REDIRECT = 1
FORMAT_IMAGE = 2
FORMAT_TRACKING_PIXEL = 3            # показы и клики
FORMAT_TRACKING_VISIBILITY = 4       # показы, клики И ВИДИМОСТЬ — наш случай
FORMAT_CLICK_PIXEL = 5
FORMAT_VAST = 6

DELIVERY_FORMATS = {
    FORMAT_REDIRECT: "Redirect",
    FORMAT_IMAGE: "Image",
    FORMAT_TRACKING_PIXEL: "Impression/Click tracking pixel",
    FORMAT_TRACKING_VISIBILITY: "Impression/Click/Visibility tracking pixel",
    FORMAT_CLICK_PIXEL: "Click tracking pixel",
    FORMAT_VAST: "VAST",
}

# Что берём по умолчанию: медийная кампания и пиксель С ВИДИМОСТЬЮ. Видимость и есть
# причина, по которой верификатор вообще подключается — брать формат без неё значит
# платить за измерение и не получать измеряемое.
DEFAULT_CHANNEL = CHANNEL_DISPLAY
DEFAULT_DELIVERY_FORMAT = FORMAT_TRACKING_VISIBILITY
