from sqlalchemy.orm import Session

from app.modules.content.models import ContentExtraction


class ContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, extraction_id: str) -> ContentExtraction | None:
        return self.session.get(ContentExtraction, extraction_id)

    def add(self, extraction: ContentExtraction) -> ContentExtraction:
        self.session.add(extraction)
        self.session.flush()
        return extraction
