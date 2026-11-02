from sqlalchemy.orm import Session

from app.modules.material.models import Material


class MaterialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, material_id: str) -> Material | None:
        return self.session.get(Material, material_id)

    def add(self, material: Material) -> Material:
        self.session.add(material)
        self.session.flush()
        return material
