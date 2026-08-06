from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Article, ArticleGroup, Operation, User
from app.routers.auth import get_current_user
from app.permissions import require_permission
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class ArticleCreate(BaseModel):
    name: str
    group: Optional[str] = None
    type: str = "expense"

class ArticleMove(BaseModel):
    direction: str  # "up" | "down"

class ArticleGroupCreate(BaseModel):
    name: str

class ArticleReorder(BaseModel):
    ids: list[int]  # полный список id статей в новом порядке

# ===================== Перестановка порядка статей (drag-and-drop) =====================
# Роут объявлен ДО /{article_id}, чтобы путь /reorder не перехватывался параметром article_id.

@router.put("/reorder")
def reorder_articles(
    data: ArticleReorder,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "edit"))
):
    """Переставляет статьи в порядке, заданном списком ids: sort_order = позиция в списке.
    Заменяет попарные перестановки (/move) — позволяет перетаскивать строку на любую позицию."""
    ids = data.ids or []
    id_to_order = {aid: idx for idx, aid in enumerate(ids)}
    articles = db.query(Article).filter(Article.id.in_(ids)).all()
    for a in articles:
        a.sort_order = id_to_order[a.id]
    db.commit()
    return {"message": "Порядок обновлён"}

# ===================== Справочник групп статей =====================
# Группы статей верхнего уровня. Хранятся в отдельной таблице article_groups как канонический
# список допустимых имён (для строгого выпадающего списка при создании/редактировании статьи).
# Роуты объявлены ДО /{article_id}, чтобы путь /groups не перехватывался параметром article_id.

@router.get("/groups")
def get_article_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Все группы из справочника. Открыт любому авторизованному — используется в выпадающих
    списках. Порядок: sort_order, затем имя."""
    rows = db.query(ArticleGroup).order_by(ArticleGroup.sort_order, ArticleGroup.name).all()
    return {"items": [{"id": g.id, "name": g.name, "sort_order": g.sort_order} for g in rows]}

@router.post("/groups")
def create_article_group(
    data: ArticleGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "edit"))
):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название группы не может быть пустым")
    existing = db.query(ArticleGroup).filter(func.lower(ArticleGroup.name) == name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Группа «{existing.name}» уже существует")
    max_order = db.query(func.max(ArticleGroup.sort_order)).scalar() or 0
    group = ArticleGroup(name=name, sort_order=max_order + 1)
    db.add(group)
    db.commit()
    db.refresh(group)
    return {"id": group.id, "message": "Группа создана"}

@router.delete("/groups/{group_id}")
def delete_article_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "edit"))
):
    group = db.query(ArticleGroup).filter(ArticleGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    used = db.query(func.count(Article.id)).filter(Article.group == group.name).scalar()
    if used:
        raise HTTPException(status_code=400, detail=f"Нельзя удалить — группа используется в {used} статьях")
    db.delete(group)
    db.commit()
    return {"message": "Группа удалена"}

# ===================== Список для выпадающих списков (/operations и т.п.) =====================
# Открыт любому авторизованному пользователю — как и раньше. Порядок теперь соответствует
# sort_order (управляется через справочник статей в Настройки → Справочники → Статьи).

@router.get("/")
def get_articles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items = db.query(Article).order_by(Article.sort_order, Article.id).all()
    return [{"id": a.id, "name": a.name, "group": a.group, "type": a.type} for a in items]


# ===================== Справочник статей (Настройки → Справочники → Статьи) =====================
# Создание/редактирование/удаление/изменение порядка — только у тех, кому выдано право
# 'articles' → 'edit'. Просмотр реестра — 'articles' → 'view'.

@router.get("/registry")
def get_articles_registry(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "view"))
):
    rows = (
        db.query(Article, func.count(Operation.id).label("op_count"))
        .outerjoin(Operation, Operation.article_id == Article.id)
        .group_by(Article.id)
        .order_by(Article.sort_order, Article.id)
        .all()
    )
    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "group": a.group,
                "type": a.type,
                "sort_order": a.sort_order,
                "op_count": op_count,
            }
            for a, op_count in rows
        ]
    }

@router.post("/")
def create_article(
    data: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "edit"))
):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    existing = db.query(Article).filter(Article.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Статья уже существует")
    max_order = db.query(func.max(Article.sort_order)).scalar() or 0
    article = Article(name=name, group=data.group, type=data.type, sort_order=max_order + 1)
    db.add(article)
    db.commit()
    db.refresh(article)
    return {"id": article.id, "message": "Статья создана"}

@router.put("/{article_id}")
def update_article(
    article_id: int,
    data: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "edit"))
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    if name != article.name:
        dup = db.query(Article).filter(Article.name == name, Article.id != article_id).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Статья «{name}» уже существует")
    article.name = name
    article.group = data.group
    article.type = data.type
    db.commit()
    return {"message": "Статья обновлена"}

@router.put("/{article_id}/move")
def move_article(
    article_id: int,
    data: ArticleMove,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "edit"))
):
    """Меняет порядок вывода — переставляет статью на одну позицию вверх/вниз,
    меняя sort_order местами с соседней статьёй в полном (несортированном поиском) списке."""
    if data.direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction должен быть 'up' или 'down'")
    ordered = db.query(Article).order_by(Article.sort_order, Article.id).all()
    idx = next((i for i, a in enumerate(ordered) if a.id == article_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    swap_idx = idx - 1 if data.direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(ordered):
        return {"message": "Статья уже на краю списка"}
    a, b = ordered[idx], ordered[swap_idx]
    a.sort_order, b.sort_order = b.sort_order, a.sort_order
    db.commit()
    return {"message": "Порядок обновлён"}

@router.delete("/{article_id}")
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_articles", "edit"))
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    op_count = db.query(func.count(Operation.id)).filter(Operation.article_id == article_id).scalar()
    if op_count:
        raise HTTPException(status_code=400, detail=f"Нельзя удалить — статья используется в {op_count} операциях")
    db.delete(article)
    db.commit()
    return {"message": "Статья удалена"}
