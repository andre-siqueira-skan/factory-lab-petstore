from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import Base, Pet, SessionLocal, engine

Status = Literal["available", "pending", "sold"]


class PetIn(BaseModel):
    name: str
    species: str
    status: Status = "available"


class PetOut(PetIn):
    id: int


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Pet Store", lifespan=lifespan)


def get_session():
    with SessionLocal() as session:
        yield session


def to_out(pet: Pet) -> PetOut:
    return PetOut(id=pet.id, name=pet.name, species=pet.species, status=pet.status)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/pets", status_code=201)
def create_pet(body: PetIn, session: Session = Depends(get_session)) -> PetOut:
    pet = Pet(**body.model_dump())
    session.add(pet)
    session.commit()
    return to_out(pet)


@app.get("/pets")
def list_pets(
    status: Status | None = None, session: Session = Depends(get_session)
) -> list[PetOut]:
    query = session.query(Pet)
    if status:
        query = query.filter(Pet.status == status)
    return [to_out(p) for p in query.order_by(Pet.id)]


@app.get("/pets/{pet_id}")
def get_pet(pet_id: int, session: Session = Depends(get_session)) -> PetOut:
    pet = session.get(Pet, pet_id)
    if pet is None:
        raise HTTPException(404, "pet not found")
    return to_out(pet)


@app.delete("/pets/{pet_id}", status_code=204)
def delete_pet(pet_id: int, session: Session = Depends(get_session)) -> None:
    pet = session.get(Pet, pet_id)
    if pet is None:
        raise HTTPException(404, "pet not found")
    session.delete(pet)
    session.commit()
