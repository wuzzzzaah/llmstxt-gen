import express from "express";

const app = express();

/**
 * List all users.
 */
app.get("/users", async (req, res) => {
    res.json([]);
});

/**
 * Create a new user.
 */
app.post("/users", async (req, res) => {
    res.status(201).json({ id: 1 });
});

app.put("/users/:id", updateUser);

app.delete("/users/:id", async (req, res) => {
    res.status(204).send();
});

async function updateUser(req: express.Request, res: express.Response) {
    res.json({ updated: true });
}

export default app;
