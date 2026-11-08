from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal, Union
from uuid import UUID

RelationType = Literal["ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY"]
Anchor = Literal["left", "right", "top", "bottom"]


class RelacionCreate(BaseModel):
    from_class: UUID
    to_class: UUID
    type: RelationType
    label: Optional[str] = None

    src_anchor: Anchor = "right"
    dst_anchor: Anchor = "left"
    src_offset: int = 0
    dst_offset: int = 0
    src_lane: int = 0
    dst_lane: int = 0

    # multiplicidad (solo válida para Association/Aggregation/Composition)
    src_mult_min: Optional[int] = 1
    src_mult_max: Optional[Union[int, Literal["*"]]] = None
    dst_mult_min: Optional[int] = 1
    dst_mult_max: Optional[Union[int, Literal["*"]]] = None

    es_clase_asociacion: bool = False

    @field_validator("src_offset", "dst_offset", "src_lane", "dst_lane", "src_mult_min", "dst_mult_min")
    @classmethod
    def non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("debe ser >= 0")
        return v

    @field_validator("src_mult_max", "dst_mult_max", mode="before")
    @classmethod
    def star_to_none(cls, v):
        if v in (None, "", "*"):
            return None
        return int(v)

    @model_validator(mode="after")
    def normalize_multiplicity(self):
        if self.type in ("DEPENDENCY", "INHERITANCE"):
            # fuerza a null (no aplica)
            self.src_mult_min = 1
            self.src_mult_max = 1
            self.dst_mult_min = 1
            self.dst_mult_max = 1
        else:
            # validaciones normales
            if isinstance(self.src_mult_max, int) and isinstance(self.src_mult_min, int):
                if self.src_mult_max < self.src_mult_min:
                    raise ValueError("src_mult_max debe ser >= src_mult_min")
            if isinstance(self.dst_mult_max, int) and isinstance(self.dst_mult_min, int):
                if self.dst_mult_max < self.dst_mult_min:
                    raise ValueError("dst_mult_max debe ser >= dst_mult_min")
        return self


class RelacionUpdate(BaseModel):
    type: Optional[RelationType] = None
    label: Optional[str] = None
    src_anchor: Optional[Anchor] = None
    dst_anchor: Optional[Anchor] = None
    src_offset: Optional[int] = None
    dst_offset: Optional[int] = None
    src_lane: Optional[int] = None
    dst_lane: Optional[int] = None

    src_mult_min: Optional[int] = None
    src_mult_max: Optional[Union[int, Literal["*"]]] = None
    dst_mult_min: Optional[int] = None
    dst_mult_max: Optional[Union[int, Literal["*"]]] = None

    @field_validator("src_offset", "dst_offset", "src_lane", "dst_lane", "src_mult_min", "dst_mult_min")
    @classmethod
    def non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("debe ser >= 0")
        return v

    @field_validator("src_mult_max", "dst_mult_max", mode="before")
    @classmethod
    def star_to_none(cls, v):
        if v in (None, "", "*"):
            return None
        return int(v)

    @model_validator(mode="after")
    def normalize_multiplicity_update(self):
        if self.type in ("DEPENDENCY", "INHERITANCE"):
            self.src_mult_min = 1
            self.src_mult_max = 1
            self.dst_mult_min = 1
            self.dst_mult_max = 1
        else:
            if self.src_mult_min is not None and self.src_mult_max is not None:
                if self.src_mult_max < self.src_mult_min:
                    raise ValueError("src_mult_max debe ser >= src_mult_min")
            if self.dst_mult_min is not None and self.dst_mult_max is not None:
                if self.dst_mult_max < self.dst_mult_min:
                    raise ValueError("dst_mult_max debe ser >= dst_mult_min")
        return self


class RelacionOut(BaseModel):
    id: UUID
    from_class: UUID = Field(alias="origen_id")
    to_class: UUID = Field(alias="destino_id")
    type: RelationType = Field(alias="tipo")
    label: Optional[str] = Field(default=None, alias="etiqueta")

    src_anchor: Anchor
    dst_anchor: Anchor
    src_offset: int
    dst_offset: int
    src_lane: int
    dst_lane: int

    src_mult_min: Optional[int] = Field(alias="mult_origen_min")
    src_mult_max: Optional[Union[int, str]] = Field(alias="mult_origen_max")
    dst_mult_min: Optional[int] = Field(alias="mult_destino_min")
    dst_mult_max: Optional[Union[int, str]] = Field(alias="mult_destino_max")

    es_clase_asociacion: bool = False

    # 🔹 Nombres de las clases
    origen_nombre: str
    destino_nombre: str
    
    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
    @model_validator(mode="after")
    def normalize_star(self):
        if self.src_mult_max is None:
            self.src_mult_max = "*"
        if self.dst_mult_max is None:
            self.dst_mult_max = "*"
        return self


