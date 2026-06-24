from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Article, Operation, User
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
    current_user: User = Depends(require_permission("articles", "view"))
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
    current_user: User = Depends(require_permission("articles", "edit"))
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
    current_user: User = Depends(require_permission("articles", "edit"))
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
    current_user: User = Depends(require_permission("articles", "edit"))
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
    current_user: User = Depends(require_permission("articles", "edit"))
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
