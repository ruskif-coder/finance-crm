"""Скриншоты: имя по цепочке и пережатие. Оба правила проверяются входом и выходом.

Картинки собираются кодом, а не лежат в фикстурах: фикстура-скриншот весила бы мегабайт,
а шум для проверки «стало меньше» проще нарисовать, чем хранить.
"""
import io

from app.traffic import files as tf


def _noisy_png(w=2400, h=1200):
    """PNG с шумом: ровная заливка сжимается в килобайты и врёт про выигрыш WebP.

    Первый замер конвертации был сделан именно на плоской картинке и показал, что WebP
    «почти не выигрывает». На настоящих файлах разрыв оказался шестикратным.
    """
    from PIL import Image
    import random
    rnd = random.Random(17)
    img = Image.new("RGB", (w, h))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                 for _ in range(w * h)])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── имя ──────────────────────────────────────────────────────────────────────
def test_name_carries_the_whole_chain():
    assert tf.traffic_file_name("HCLA6E", "SMK1", 2, 1, ".webp") == "HCLA6E-SMK1-cr2-01.webp"


def test_cr_prefix_makes_the_name_unambiguous():
    """Без `cr` имя неотличимо от кода пары с лишним числом."""
    assert "cr" in tf.traffic_file_name("HCLA6E", "SMK1", 2, 1, ".webp")


def test_cyrillic_and_symbols_never_reach_the_name():
    """Архив уходит клиенту, а кириллица внутри zip ломается у части распаковщиков."""
    assert tf.traffic_file_name("HCLA-6E", "SM@K 1", 3, 7, ".webp") == "HCLA6E-SMK1-cr3-07.webp"


def test_code_that_vanishes_after_cleanup_is_replaced_not_dropped():
    """Целиком кириллический код очищается в пустоту. Пустой кусок обязан заменяться
    запасным, иначе имя схлопывается в цепочку дефисов и перестаёт быть именем."""
    assert tf.traffic_file_name("СДЕЛКА", "ПЛОЩАДКА", 3, 7, ".webp") == "deal-site-cr3-07.webp"


def test_order_by_name_matches_order_of_upload():
    names = [tf.traffic_file_name("D", "P", 1, i, ".webp") for i in (1, 2, 10, 11)]
    assert names == sorted(names), "двузначный номер обязан быть с ведущим нулём"


# ── пережатие ────────────────────────────────────────────────────────────────
def test_png_becomes_smaller_webp():
    src = _noisy_png()
    out, ext, ctype = tf.convert(src, ".png")
    assert ext == ".webp" and ctype == "image/webp"
    assert len(out) < len(src)


def test_long_side_is_capped():
    from PIL import Image
    out, _ext, _ct = tf.convert(_noisy_png(3000, 1000), ".png")
    assert max(Image.open(io.BytesIO(out)).size) <= tf.MAX_SIDE


def test_pdf_is_never_touched():
    src = b"%PDF-1.4 fake"
    out, ext, ctype = tf.convert(src, ".pdf")
    assert out == src and ext == ".pdf" and ctype == "application/pdf"


def test_already_compressed_file_is_kept_as_is():
    """Правило «не стало меньше — кладём исходник»: класть больший файл вместо меньшего
    было бы прямым вредом, а такое случается с уже пережатыми скриншотами."""
    from PIL import Image
    img = Image.new("RGB", (40, 30), (200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=40)
    src = buf.getvalue()
    out, _ext, _ct = tf.convert(src, ".webp")
    assert out == src


def test_broken_file_is_stored_rather_than_refused():
    """Не смогли пережать — не повод отказать в приёме доказательства."""
    src = b"not an image at all"
    out, ext, _ct = tf.convert(src, ".png")
    assert out == src and ext == ".png"


def test_limit_is_ten():
    assert tf.MAX_PAIR_FILES == 10, (
        "предел согласован владельцем: снимают 3–5 кадров, 10 — запас от выгрузки папки")
