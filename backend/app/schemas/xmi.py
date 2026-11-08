from pydantic import BaseModel


class XmiImportSummary(BaseModel):
    classes_created: list[str] = []
    classes_skipped: list[str] = []
    attributes_created: int = 0
    attributes_skipped: int = 0
    methods_created: int = 0
    methods_skipped: int = 0
    relations_created: int = 0
    relations_skipped: int = 0
    warnings: list[str] = []
