from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.indicator import Indicator
from app.schemas.indicator import IndicatorOut, IndicatorUpdate
from app.agents.indicator_agent import generate_indicators

router = APIRouter(tags=["indicators"])

@router.post("/queries/{query_id}/indicators/generate", response_model=List[IndicatorOut])
async def generate_indicator_draft(query_id: int, db: Session = Depends(get_db)):
    from app.models.tech_query import TechQuery
    query = db.query(TechQuery).filter(TechQuery.id == query_id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    drafts = await generate_indicators(query.category, query.description)
    indicators = []
    for d in drafts:
        ind = Indicator(
            query_id=query_id,
            name=d["name"],
            unit=d.get("unit"),
            description=d.get("description"),
            search_keywords=d.get("search_keywords"),
            extraction_hint=d.get("extraction_hint"),
        )
        db.add(ind)
        indicators.append(ind)
    db.commit()
    for ind in indicators:
        db.refresh(ind)
    return indicators

@router.put("/indicators/{indicator_id}", response_model=IndicatorOut)
def update_indicator(indicator_id: int, payload: IndicatorUpdate, db: Session = Depends(get_db)):
    ind = db.query(Indicator).filter(Indicator.id == indicator_id).first()
    if not ind:
        raise HTTPException(status_code=404, detail="Indicator not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(ind, field, val)
    db.commit()
    db.refresh(ind)
    return ind

@router.delete("/indicators/{indicator_id}", status_code=204)
def delete_indicator(indicator_id: int, db: Session = Depends(get_db)):
    ind = db.query(Indicator).filter(Indicator.id == indicator_id).first()
    if not ind:
        raise HTTPException(status_code=404, detail="Indicator not found")
    db.delete(ind)
    db.commit()
