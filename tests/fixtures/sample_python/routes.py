from fastapi import FastAPI, APIRouter

app = FastAPI()
router = APIRouter()

@app.get("/users")
async def list_users():
    """List all users."""
    return []

@router.post(path="/users/{id}")
def create_user(id: str):
    """Create a user."""
    return {"id": id}

@app.route("/legacy", methods=("GET", "POST"))
def legacy_route():
    """Old school Flask style in FastAPI or just Flask."""
    return "ok"

@app.put("/items/{item_id}")
@app.patch("/items/{item_id}")
def update_item(item_id: int):
    return {"item_id": item_id}
