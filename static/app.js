// app.js — browser chat UI for Jarvis, talking to the FastAPI backend
// in server.py: /api/chat, /api/vision, /api/settings, /api/conversations.

const chatLog = document.getElementById("chatLog");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const webcamBtn = document.getElementById("webcamBtn");
const screenBtn = document.getElementById("screenBtn");
const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");
const clearBtn = document.getElementById("clearBtn");
const helpBtn = document.getElementById("helpBtn");
const settingsBtn = document.getElementById("settingsBtn");
const clockEl = document.getElementById("clock");
const assistantNameEl = document.getElementById("assistantName");
const newChatBtn = document.getElementById("newChatBtn");
const conversationListEl = document.getElementById("conversationList");
const logoutBtn = document.getElementById("logoutBtn");

let assistantName = "Jarvis";
let currentConversationId = null;

// ------------------------------------------------------------------ clock
function tickClock() {
  const now = new Date();
  clockEl.textContent = now.toLocaleString(undefined, {
    weekday: "short", day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit",
  });
}
tickClock();
setInterval(tickClock, 1000 * 30);

// -------------------------------------------------------------------- log
function addMessage(speaker, text, { imageUrl, pending } = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${speaker === "You" ? "user" : "assistant"}`;

  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.textContent = `${speaker} · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  wrap.appendChild(meta);

  if (imageUrl) {
    const img = document.createElement("img");
    img.className = "msg-image";
    img.src = imageUrl;
    wrap.appendChild(img);
  }

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  if (pending) {
    bubble.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
  } else {
    bubble.textContent = text;
  }
  wrap.appendChild(bubble);

  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
  return bubble;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

// ------------------------------------------------------------ conversations
async function fetchConversations() {
  try {
    const res = await fetch("/api/conversations");
    if (!res.ok) return [];
    return await res.json();
  } catch (_) {
    return [];
  }
}

function renderConversationList(conversations) {
  conversationListEl.innerHTML = "";
  for (const conv of conversations) {
    const item = document.createElement("div");
    item.className = "conv-item" + (conv.id === currentConversationId ? " active" : "");
    item.dataset.id = conv.id;

    const title = document.createElement("span");
    title.className = "conv-item-title";
    title.textContent = conv.title || "New chat";
    item.appendChild(title);

    const del = document.createElement("button");
    del.className = "conv-item-delete";
    del.type = "button";
    del.title = "Delete chat";
    del.textContent = "×";
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteConversation(conv.id);
    });
    item.appendChild(del);

    item.addEventListener("click", () => selectConversation(conv.id));
    conversationListEl.appendChild(item);
  }
}

async function refreshConversationList() {
  const conversations = await fetchConversations();
  renderConversationList(conversations);
  return conversations;
}

async function selectConversation(convId) {
  try {
    const res = await fetch(`/api/conversations/${convId}`);
    if (!res.ok) throw new Error("couldn't load that chat");
    const conv = await res.json();
    currentConversationId = conv.id;
    chatLog.innerHTML = "";
    if (conv.messages && conv.messages.length) {
      for (const m of conv.messages) {
        addMessage(m.speaker === "user" ? "You" : assistantName, m.text);
      }
    } else {
      greet();
    }
    highlightActiveConversation();
  } catch (err) {
    toast("Couldn't load that chat.");
  }
}

function highlightActiveConversation() {
  for (const item of conversationListEl.children) {
    item.classList.toggle("active", item.dataset.id === currentConversationId);
  }
}

async function startNewConversation() {
  try {
    const res = await fetch("/api/conversations", { method: "POST" });
    if (!res.ok) throw new Error("couldn't start a new chat");
    const conv = await res.json();
    currentConversationId = conv.id;
    chatLog.innerHTML = "";
    greet();
    await refreshConversationList();
  } catch (err) {
    toast("Couldn't start a new chat.");
  }
}

async function deleteConversation(convId) {
  try {
    const res = await fetch(`/api/conversations/${convId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("delete failed");
    const wasActive = convId === currentConversationId;
    const conversations = await refreshConversationList();
    if (wasActive) {
      if (conversations.length) {
        await selectConversation(conversations[0].id);
      } else {
        await startNewConversation();
      }
    }
  } catch (err) {
    toast("Couldn't delete that chat.");
  }
}

newChatBtn.addEventListener("click", startNewConversation);

if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/login";
    }
  });
}

// -------------------------------------------------------------- api calls
async function sendChat(text) {
  const pendingBubble = addMessage(assistantName, "", { pending: true });
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, conversation_id: currentConversationId }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "request failed");
    const data = await res.json();
    pendingBubble.textContent = data.reply;
    speak(data.reply);

    const isNewConversation = currentConversationId !== data.conversation_id;
    currentConversationId = data.conversation_id;
    if (isNewConversation) {
      await refreshConversationList();
    } else {
      // Title may have just been auto-generated from this first message,
      // or the "updated" ordering changed -- refresh the list either way.
      await refreshConversationList();
    }
  } catch (err) {
    pendingBubble.textContent = `Sorry, something went wrong: ${err.message}`;
  }
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function sendImage(blob, source, imageUrl) {
  addMessage("You", `[${source}]`, { imageUrl });
  const pendingBubble = addMessage(assistantName, "", { pending: true });
  try {
    const form = new FormData();
    form.append("image", blob, `${source.replace(/\s+/g, "_")}.jpg`);
    form.append("source", source);
    if (currentConversationId) form.append("conversation_id", currentConversationId);
    const res = await fetch("/api/vision", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail || "request failed");
    const data = await res.json();
    pendingBubble.textContent = data.reply;
    speak(data.reply);
    currentConversationId = data.conversation_id;
    await refreshConversationList();
  } catch (err) {
    pendingBubble.textContent = `Sorry, I couldn't analyze that: ${err.message}`;
  }
  chatLog.scrollTop = chatLog.scrollHeight;
}

// ---------------------------------------------------------------- sending
function handleSend() {
  const text = textInput.value.trim();
  if (!text) return;
  textInput.value = "";
  addMessage("You", text);
  sendChat(text);
}
sendBtn.addEventListener("click", handleSend);
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleSend();
});

clearBtn.addEventListener("click", () => {
  chatLog.innerHTML = "";
  greet();
});

helpBtn.addEventListener("click", () => {
  addMessage("You", "help");
  sendChat("help");
});

function greet() {
  addMessage(assistantName, `Hi, I'm online. Type 'help' to see everything I can do, or just ask me something.`);
}

// -------------------------------------------------------- text-to-speech
function speak(text) {
  if (!("speechSynthesis" in window)) return;
  try {
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1.0;
    window.speechSynthesis.speak(utter);
  } catch (_) { /* non-fatal */ }
}

// -------------------------------------------------------- speech-to-text
const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let listening = false;

if (SpeechRecognitionImpl) {
  recognizer = new SpeechRecognitionImpl();
  recognizer.continuous = false;
  recognizer.interimResults = false;
  recognizer.lang = "en-US";

  recognizer.onresult = (event) => {
    const heard = event.results[0][0].transcript;
    addMessage("You", heard);
    sendChat(heard);
  };
  recognizer.onerror = () => toast("I didn't catch that.");
  recognizer.onend = () => {
    listening = false;
    micBtn.classList.remove("active");
    micBtn.textContent = "🎤";
  };
} else {
  micBtn.disabled = true;
  micBtn.title = "Voice input isn't supported in this browser";
}

micBtn.addEventListener("click", () => {
  if (!recognizer || listening) return;
  listening = true;
  micBtn.classList.add("active");
  micBtn.textContent = "…";
  recognizer.start();
});

// -------------------------------------------------------------- webcam
const webcamModal = document.getElementById("webcamModal");
const webcamVideo = document.getElementById("webcamVideo");
const webcamCanvas = document.getElementById("webcamCanvas");
let webcamStream = null;

async function openWebcam() {
  try {
    webcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
    webcamVideo.srcObject = webcamStream;
    webcamModal.classList.remove("hidden");
  } catch (err) {
    toast("Couldn't access the webcam — check browser permissions.");
  }
}

function closeWebcam() {
  if (webcamStream) {
    webcamStream.getTracks().forEach((t) => t.stop());
    webcamStream = null;
  }
  webcamModal.classList.add("hidden");
}

document.getElementById("webcamCancel").addEventListener("click", closeWebcam);
webcamBtn.addEventListener("click", openWebcam);

document.getElementById("webcamCapture").addEventListener("click", () => {
  const w = webcamVideo.videoWidth, h = webcamVideo.videoHeight;
  webcamCanvas.width = w;
  webcamCanvas.height = h;
  webcamCanvas.getContext("2d").drawImage(webcamVideo, 0, 0, w, h);
  webcamCanvas.toBlob((blob) => {
    const url = URL.createObjectURL(blob);
    sendImage(blob, "webcam snapshot", url);
    closeWebcam();
  }, "image/jpeg", 0.9);
});

// -------------------------------------------------------------- screen
screenBtn.addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    const track = stream.getVideoTracks()[0];
    const capture = new ImageCapture(track);
    const bitmap = await capture.grabFrame();
    track.stop();

    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      sendImage(blob, "screenshot", url);
    }, "image/jpeg", 0.9);
  } catch (err) {
    toast("Screen capture was cancelled or isn't available.");
  }
});

// -------------------------------------------------------------- upload
uploadBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  sendImage(file, "uploaded image", url);
  fileInput.value = "";
});

// ------------------------------------------------------------- settings
const settingsModal = document.getElementById("settingsModal");
const setUserName = document.getElementById("setUserName");
const setAssistantName = document.getElementById("setAssistantName");
const setCity = document.getElementById("setCity");
const setNewsCountry = document.getElementById("setNewsCountry");
const setGroqKey = document.getElementById("setGroqKey");
const setGroqModel = document.getElementById("setGroqModel");

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const cfg = await res.json();
    assistantName = cfg.assistant_name || "Jarvis";
    assistantNameEl.textContent = assistantName;
    document.title = assistantName;
    return cfg;
  } catch (_) {
    return {};
  }
}

settingsBtn.addEventListener("click", async () => {
  const cfg = await loadSettings();
  setUserName.value = cfg.user_name === "there" ? "" : (cfg.user_name || "");
  setAssistantName.value = cfg.assistant_name || "";
  setCity.value = cfg.city || "";
  setNewsCountry.value = cfg.news_country || "";
  setGroqKey.value = "";
  setGroqKey.placeholder = cfg.groq_api_key ? `saved (${cfg.groq_api_key})` : "gsk_...";
  setGroqModel.value = cfg.groq_model || "";
  settingsModal.classList.remove("hidden");
});

document.getElementById("settingsCancel").addEventListener("click", () => {
  settingsModal.classList.add("hidden");
});

document.getElementById("settingsSave").addEventListener("click", async () => {
  const payload = {
    user_name: setUserName.value.trim() || null,
    assistant_name: setAssistantName.value.trim() || null,
    city: setCity.value.trim() || null,
    news_country: setNewsCountry.value.trim() || null,
    groq_model: setGroqModel.value.trim() || null,
  };
  if (setGroqKey.value.trim()) payload.groq_api_key = setGroqKey.value.trim();

  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadSettings();
    toast("Settings saved.");
  } catch (_) {
    toast("Couldn't save settings.");
  }
  settingsModal.classList.add("hidden");
});

// ------------------------------------------------------------------ init
(async function init() {
  await loadSettings();

  const conversations = await refreshConversationList();
  if (conversations.length) {
    await selectConversation(conversations[0].id);
  } else {
    await startNewConversation();
  }

  if (!webcamBtn) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) webcamBtn.disabled = true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) screenBtn.disabled = true;
})();
