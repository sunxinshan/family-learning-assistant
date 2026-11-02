from fastapi import APIRouter, Depends, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, get_runtime_context
from app.modules.material.repository import MaterialRepository
from app.modules.material.schemas import MaterialOut
from app.modules.material.service import MaterialService

router = APIRouter(tags=["material"])


@router.post("/materials", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def upload_material(
    request: Request,
    file: UploadFile,
    context: RuntimeContext = Depends(get_runtime_context),
    session: Session = Depends(get_session),
) -> MaterialOut:
    service = MaterialService(MaterialRepository(session), request.app.state.settings)
    material = await service.upload(context.user_id, file)
    return MaterialOut.model_validate(material)
