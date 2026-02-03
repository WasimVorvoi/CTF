const express = require("express");
const cors = require("cors");

const app = express();
app.use(cors());
app.use(express.json());

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

app.post("/bestmove", (req, res) => {
  res.json({ bestmove: "e2e4" });
});

const port = process.env.PORT || 5501;
app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Stockfish wrapper listening on ${port}`);
});
