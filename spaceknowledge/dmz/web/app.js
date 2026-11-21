"use strict";

/*
  The browser client for Space Knowledge.

  Nothing here is a control. Every rule below is enforced again by the server;
  the checks only save a round trip. Delete this file's checks and the server
  would behave exactly the same.

  Everything the game says is put on the page with textContent, never as markup,
  so nothing a player types (or the game replies) can run as script.
*/

const MAX_LINE = 200;
const TOKEN_KEY = "sk-token";

const $ = (id) => document.getElementById(id);
let token = "";

// ---------------------------------------------------------------- session

function loadToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch (problem) { return ""; }
}

function saveToken(value) {
  token = value;
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch (problem) {
    // Some private windows refuse storage: the session just will not survive a refresh.
  }
}

// ---------------------------------------------------------------- showing things

function setStatus(text) {
  $("status").textContent = text || "";
}

function write(text, kind) {
  const line = document.createElement("div");
  line.textContent = text;
  if (kind) line.className = kind;
  const box = $("console");
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function describeRefusal(refusal) {
  if (!refusal) return "The game sent an answer this page cannot read.";
  return "Refused: " + refusal.what + ". Why: " + refusal.why + ". Next: " + refusal.next_step + ".";
}

function fillList(id, entries, emptyText) {
  const list = $(id);
  list.replaceChildren();
  const shown = entries.length ? entries : [emptyText];
  for (const text of shown) {
    const item = document.createElement("li");
    item.textContent = text;
    if (!entries.length) item.className = "empty";
    list.appendChild(item);
  }
}

function showGame(visible) {
  $("login-panel").hidden = visible;
  $("game").hidden = !visible;
}

// The same rule as `slug` in spaceknowledge/tests/dmz/test_web_files.py:
// "The Moon" becomes "moon", so the page needs a ".planet-moon" background.
function slug(name) {
  return name.toLowerCase().trim().replace(/^the\s+/, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function setPlace(name) {
  $("where").textContent = name;
  document.body.className = "planet-" + (slug(name) || "space");
}

// ---------------------------------------------------------------- talking to the DMZ

async function api(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = "Bearer " + token;
  let response;
  try {
    response = await fetch(path, { method: "POST", headers: headers, body: JSON.stringify(body) });
  } catch (problem) {
    throw new Error("Cannot reach the game. Check that it is running, then try again.");
  }
  let data;
  try {
    data = await response.json();
  } catch (problem) {
    throw new Error("The game sent an answer this page cannot read.");
  }
  return { status: response.status, data: data };
}

async function guarded(action) {
  try {
    await action();
  } catch (problem) {
    setStatus(problem.message);
  }
}

function endSession(refusal) {
  saveToken("");
  showGame(false);
  document.body.className = "planet-space";
  setStatus(describeRefusal(refusal));
}

// The reply text, or null when nothing should be shown (the session ended, or
// the request itself was refused and the status line already says why).
async function send(line) {
  const result = await api("/command", { line: line });
  if (result.status === 401) {
    endSession(result.data.refusal);
    return null;
  }
  if (!result.data.ok) {
    setStatus(describeRefusal(result.data.refusal));
    return null;
  }
  return result.data.reply;
}

// ---------------------------------------------------------------- the side panel

function parseInventory(text) {
  const items = [];
  const resources = [];
  for (const line of text.split("\n")) {
    if (line.startsWith("You are carrying: ")) items.push(...line.slice(18).split(", "));
    else if (line.startsWith("Resources: ")) resources.push(...line.slice(11).split(", "));
  }
  return { items: items, resources: resources };
}

function showMission(text) {
  const lines = text.split("\n");
  const match = /^Mission: (.+) \((\w+)\)$/.exec(lines[0]);
  $("mission").textContent = match ? match[1] + " - " + match[2] : "none";
  $("mission-detail").textContent = match && lines[1] ? lines[1] : "";
}

async function refreshPanel() {
  const place = await send("where");
  if (place === null) return;
  const match = /^You are at (.+)\.$/.exec(place);
  if (match) setPlace(match[1]);   // a refusal does not match, so the old background stays

  const stuff = await send("inventory");
  if (stuff === null) return;
  if (!stuff.startsWith("Refused")) {
    const parsed = parseInventory(stuff);
    fillList("items", parsed.items, "nothing");
    fillList("resources", parsed.resources, "none");
  }

  const mission = await send("mission");
  if (mission !== null) showMission(mission);
}

async function enterGame() {
  showGame(true);
  setStatus("");
  write("Welcome. Type help to see what you can do.", "reply");
  await guarded(refreshPanel);
  $("line").focus();
}

// ---------------------------------------------------------------- the forms

async function credentials(path) {
  const username = $("username").value.trim().toLowerCase();
  const password = $("password").value;
  setStatus("");
  await guarded(async () => {
    const result = await api(path, { username: username, password: password });
    if (path === "/login") $("password").value = "";
    if (!result.data.ok) {
      setStatus(describeRefusal(result.data.refusal));
      return;
    }
    if (path === "/register") {
      setStatus("Account created. Now log in.");
      return;
    }
    saveToken(result.data.token);
    await enterGame();
  });
}

async function logout() {
  await guarded(async () => { await api("/logout", {}); });
  saveToken("");
  showGame(false);
  document.body.className = "planet-space";
  $("console").replaceChildren();
}

$("auth").addEventListener("submit", async (event) => {
  event.preventDefault();
  await credentials("/login");
});

$("register-button").addEventListener("click", async () => {
  await credentials("/register");
});

$("logout-button").addEventListener("click", logout);

$("command-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("line");
  const line = input.value.trim();
  if (!line) return;
  if (line.length > MAX_LINE) {
    setStatus("That line is longer than " + MAX_LINE + " characters.");
    return;
  }
  input.value = "";
  setStatus("");
  if (line.toLowerCase() === "quit" || line.toLowerCase() === "q") {
    await logout();
    return;
  }
  write("> " + line, "typed");
  await guarded(async () => {
    const reply = await send(line);
    if (reply === null) return;
    write(reply, reply.startsWith("Refused") ? "refused" : "reply");
    await refreshPanel();
  });
});

// ---------------------------------------------------------------- start

token = loadToken();
if (token) enterGame();   // a refresh keeps the session; a dead token is sent back to login
else showGame(false);