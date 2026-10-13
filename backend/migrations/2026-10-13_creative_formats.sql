-- Формат креатива поверхности площадки (владелец 13.10.2026).
-- Справочник типов креатива DSP и стандартный тип у каждой пары «площадка × веб/апп».
-- Типология — как в API DSP (Creative.add, поле type). Отправку не-HTML типов конвейер пока не умеет:
-- поле только фиксирует, что площадка принимает. Повторный накат безопасен.

CREATE TABLE IF NOT EXISTS ad_creative_formats (
    key        VARCHAR(16) PRIMARY KEY,          -- значение поля type в DSP
    title      VARCHAR(64) NOT NULL,
    sort_order INTEGER     NOT NULL DEFAULT 0,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    note       TEXT
);

INSERT INTO ad_creative_formats (key, title, sort_order, note) VALUES
    ('HTML',         'HTML-баннер',  10, 'html_code; size; пиксели, аудит, extension_link'),
    ('TEASER',       'Тизер',        20, 'data: title, text, iconMask/iconFormats, imgMask/imgFormats; пиксели'),
    ('VIDEO_INLINE', 'Видео',        30, 'data: video_url, video_poster_url, file_size, description, use_vpaid'),
    ('VIDEO_VAST',   'Видео VAST',   40, 'data: vast_url, description')
ON CONFLICT (key) DO NOTHING;

-- Колонка и бэкфилл Купера — один раз: повтор не должен затирать ручную правку.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'sales_publisher_surfaces' AND column_name = 'creative_format') THEN
        ALTER TABLE sales_publisher_surfaces
            ADD COLUMN creative_format VARCHAR(16) NOT NULL DEFAULT 'HTML'
            REFERENCES ad_creative_formats (key);
        UPDATE sales_publisher_surfaces s SET creative_format = 'TEASER'
          WHERE s.kind = 'app'
            AND s.publisher_id IN (SELECT id FROM sales_publishers
                                    WHERE lower(name) LIKE '%kuper%' OR lower(name) LIKE '%купер%'
                                       OR lower(coalesce(domain, '')) LIKE '%kuper%');
    END IF;
END $$;
