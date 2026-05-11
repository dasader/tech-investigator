from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tech_query import TechQuery
from app.schemas.tech_query import TechQueryCreate, TechQueryOut

router = APIRouter(tags=["tech-input"])

@router.post("/tech-input", response_model=TechQueryOut)
def create_tech_input(payload: TechQueryCreate, db: Session = Depends(get_db)):
    query = TechQuery(
        category=payload.category,
        description=payload.description,
        user_email=payload.user_email,
        search_source=payload.search_source,
    )
    db.add(query)
    db.commit()
    db.refresh(query)
    return query
