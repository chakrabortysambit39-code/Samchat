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
/* ===========================================================
   PREMIUM SYSTEM
=========================================================== */

const premiumBtn = document.getElementById("premiumBtn");
const premiumModal = document.getElementById("premiumModal");
const premiumPayBtn = document.getElementById("premiumPayBtn");
const submitTxnBtn = document.getElementById("submitTxnBtn");
const closePremiumBtn = document.getElementById("closePremiumBtn");

const txnInput = document.getElementById("txnInput");

const premiumBadge = document.getElementById("premiumBadge");
const usageBadge = document.getElementById("usageBadge");

let currentOrder = null;


/* -------------------- status ---------------------- */

async function loadPremiumStatus(){

    try{

        const r = await fetch("/api/premium/status");

        if(!r.ok) return;

        const data = await r.json();

        if(data.is_premium){

            premiumBadge.classList.remove("hidden");

            usageBadge.innerHTML="👑 Unlimited";

        }else{

            premiumBadge.classList.add("hidden");

            usageBadge.innerHTML=
            `${data.used_today}/${data.daily_limit} Free`;

        }

    }catch(e){

        console.log(e);

    }

}


/* -------------------- open modal ---------------------- */

premiumBtn.onclick=()=>{

    premiumModal.classList.remove("hidden");

};


/* -------------------- close modal ---------------------- */

closePremiumBtn.onclick=()=>{

    premiumModal.classList.add("hidden");

};


/* -------------------- create order ---------------------- */

premiumPayBtn.onclick=async()=>{

    try{

        const r=await fetch("/api/premium/create-order",{

            method:"POST"

        });

        const data=await r.json();

        currentOrder=data;

        window.open(data.upi_link,"_blank");

        toast("Complete payment then submit transaction id.");

    }

    catch{

        toast("Unable to start payment.");

    }

};


/* -------------------- submit txn ---------------------- */

submitTxnBtn.onclick=async()=>{

    if(!currentOrder){

        toast("Pay first.");

        return;

    }

    const txn=txnInput.value.trim();

    if(txn===""){

        toast("Enter transaction id.");

        return;

    }

    try{

        const r=await fetch("/api/premium/submit-txn",{

            method:"POST",

            headers:{

                "Content-Type":"application/json"

            },

            body:JSON.stringify({

                order_id:currentOrder.order_id,

                txn_ref:txn

            })

        });

        const data=await r.json();

        toast(data.message||"Submitted.");

        premiumModal.classList.add("hidden");

        txnInput.value="";

        loadPremiumStatus();

    }

    catch{

        toast("Submission failed.");

    }

};


/* -------------------- auto refresh ---------------------- */

setInterval(loadPremiumStatus,30000);

loadPremiumStatus();
/* ===========================================================
   ADMIN LOGIN
=========================================================== */

const adminLink = document.getElementById("adminLink");
const adminModal = document.getElementById("adminModal");
const adminCode = document.getElementById("adminCode");
const adminLoginBtn = document.getElementById("adminLoginBtn");
const adminCancelBtn = document.getElementById("adminCancelBtn");
const adminError = document.getElementById("adminError");

let adminKey = localStorage.getItem("admin_key") || "";

/* -------------------- open popup ---------------------- */

if (adminLink) {
    adminLink.addEventListener("click", (e) => {
        e.preventDefault();

        adminError.textContent = "";
        adminCode.value = "";

        adminModal.classList.remove("hidden");
        adminCode.focus();
    });
}

/* -------------------- close popup ---------------------- */

function closeAdminModal() {
    adminModal.classList.add("hidden");
    adminError.textContent = "";
}

if (adminCancelBtn) {
    adminCancelBtn.onclick = closeAdminModal;
}

/* close by clicking outside */

if (adminModal) {
    adminModal.addEventListener("click", (e) => {
        if (e.target === adminModal) {
            closeAdminModal();
        }
    });
}

/* ESC key */

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !adminModal.classList.contains("hidden")) {
        closeAdminModal();
    }
});

/* -------------------- validate ---------------------- */

async function validateAdmin(code) {

    const response = await fetch("/api/admin/payments/pending", {
        headers: {
            "X-Admin-Key": code
        }
    });

    return response.ok;
}

/* -------------------- login ---------------------- */

async function adminLogin() {

    const code = adminCode.value.trim();

    if (!code) {
        adminError.textContent = "Please enter Admin Code.";
        return;
    }

    adminLoginBtn.disabled = true;
    adminLoginBtn.textContent = "Checking...";

    try {

        const ok = await validateAdmin(code);

        if (!ok) {
            adminError.textContent = "Invalid Admin Code";
            return;
        }

        adminKey = code;

        localStorage.setItem("admin_key", code);

        window.location.href = "/admin";

    } catch (err) {

        console.error(err);

        adminError.textContent = "Server unavailable.";

    } finally {

        adminLoginBtn.disabled = false;
        adminLoginBtn.textContent = "Login";

    }

}

if (adminLoginBtn) {
    adminLoginBtn.onclick = adminLogin;
}

/* ENTER key */

if (adminCode) {

    adminCode.addEventListener("keydown", (e) => {

        if (e.key === "Enter") {

            adminLogin();

        }

    });

}
/* ===========================================================
   ADMIN DASHBOARD API
=========================================================== */

const API = {

    get adminKey() {
        return localStorage.getItem("admin_key") || "";
    },

    headers(extra = {}) {
        return {
            "Content-Type": "application/json",
            "X-Admin-Key": this.adminKey,
            ...extra
        };
    },

    async get(url) {

        const r = await fetch(url, {
            headers: this.headers()
        });

        if (!r.ok)
            throw new Error(await r.text());

        return await r.json();

    },

    async post(url, body = {}) {

        const r = await fetch(url, {

            method: "POST",

            headers: this.headers(),

            body: JSON.stringify(body)

        });

        if (!r.ok)
            throw new Error(await r.text());

        return await r.json();

    },

    async del(url) {

        const r = await fetch(url, {

            method: "DELETE",

            headers: this.headers()

        });

        if (!r.ok)
            throw new Error(await r.text());

        return await r.json();

    }

};


/* ===========================================================
   ADMIN FUNCTIONS
=========================================================== */


async function getPendingPayments(){

    return await API.get("/api/admin/payments/pending");

}


async function approvePayment(orderId){

    return await API.post("/api/admin/payments/approve",{

        order_id:orderId

    });

}


async function rejectPayment(orderId){

    return await API.post("/api/admin/payments/reject",{

        order_id:orderId

    });

}


async function getUsers(){

    return await API.get("/api/admin/users");

}


async function getDashboard(){

    return await API.get("/api/admin/dashboard");

}


async function getAnalytics(){

    return await API.get("/api/admin/analytics");

}


async function getRevenue(){

    return await API.get("/api/admin/revenue");

}


async function getBroadcasts(){

    return await API.get("/api/admin/broadcasts");

}


async function sendBroadcast(message){

    return await API.post("/api/admin/broadcast",{

        message

    });

}


/* ===========================================================
   ADMIN LOGOUT
=========================================================== */

function adminLogout(){

    localStorage.removeItem("admin_key");

    window.location="/login";

}


/* ===========================================================
   AUTO REDIRECT IF KEY MISSING
=========================================================== */

function requireAdmin(){

    if(!localStorage.getItem("admin_key")){

        window.location="/login";

        return false;

    }

    return true;

}
/* ===========================================================
   USER MANAGEMENT
=========================================================== */

let adminUsers = [];
let filteredUsers = [];

/* -------------------- load users ---------------------- */

async function loadUsers() {

    try {

        adminUsers = await getUsers();

        filteredUsers = [...adminUsers];

        return filteredUsers;

    } catch (err) {

        console.error(err);

        toast("Unable to load users.");

        return [];

    }

}

/* -------------------- search ---------------------- */

function searchUsers(keyword = "") {

    keyword = keyword.trim().toLowerCase();

    if (keyword === "") {

        filteredUsers = [...adminUsers];

        return filteredUsers;

    }

    filteredUsers = adminUsers.filter(user => {

        return (

            (user.email || "").toLowerCase().includes(keyword) ||

            (user.name || "").toLowerCase().includes(keyword)

        );

    });

    return filteredUsers;

}

/* -------------------- premium ---------------------- */

async function makePremium(email, days = 30) {

    try {

        await API.post("/api/admin/users/premium", {

            email,

            days

        });

        toast("Premium Activated");

        await loadUsers();

    }

    catch (err) {

        toast("Failed");

    }

}


async function removePremium(email) {

    try {

        await API.post("/api/admin/users/remove-premium", {

            email

        });

        toast("Premium Removed");

        await loadUsers();

    }

    catch (err) {

        toast("Failed");

    }

}


/* -------------------- ban ---------------------- */

async function banUser(email) {

    if (!confirm("Ban this user?"))

        return;

    try {

        await API.post("/api/admin/users/ban", {

            email

        });

        toast("User Banned");

        await loadUsers();

    }

    catch {

        toast("Failed");

    }

}


/* -------------------- unban ---------------------- */

async function unbanUser(email) {

    try {

        await API.post("/api/admin/users/unban", {

            email

        });

        toast("User Unbanned");

        await loadUsers();

    }

    catch {

        toast("Failed");

    }

}


/* -------------------- delete ---------------------- */

async function deleteUser(email) {

    if (!confirm("Delete this user permanently?"))

        return;

    try {

        await API.post("/api/admin/users/delete", {

            email

        });

        toast("User Deleted");

        await loadUsers();

    }

    catch {

        toast("Delete Failed");

    }

}


/* -------------------- reset usage ---------------------- */

async function resetUsage(email){

    try{

        await API.post("/api/admin/users/reset-usage",{

            email

        });

        toast("Usage Reset");

    }

    catch{

        toast("Failed");

    }

}


/* -------------------- details ---------------------- */

async function getUserDetails(email){

    return await API.post("/api/admin/users/details",{

        email

    });

}


/* -------------------- export csv ---------------------- */

function exportUsersCSV(){

    if(adminUsers.length===0){

        toast("No users");

        return;

    }

    let csv="Name,Email,Premium,Banned\n";

    adminUsers.forEach(u=>{

        csv+=`"${u.name||""}","${u.email}",${u.premium},${u.banned}\n`;

    });

    const blob=new Blob([csv],{

        type:"text/csv"

    });

    const url=URL.createObjectURL(blob);

    const a=document.createElement("a");

    a.href=url;

    a.download="users.csv";

    a.click();

    URL.revokeObjectURL(url);

}


/* -------------------- stats ---------------------- */

function userStats(){

    return{

        total:adminUsers.length,

        premium:adminUsers.filter(x=>x.premium).length,

        banned:adminUsers.filter(x=>x.banned).length,

        free:adminUsers.filter(x=>!x.premium).length

    };

}
/* ===========================================================
   ADMIN DASHBOARD
=========================================================== */

let dashboardData = {};
let analyticsData = {};
let revenueData = {};
let paymentData = [];

/* ---------------- Dashboard ---------------- */

async function refreshDashboard(){

    try{

        dashboardData = await getDashboard();

        return dashboardData;

    }

    catch(err){

        console.error(err);

        toast("Dashboard unavailable.");

        return {};

    }

}


/* ---------------- Analytics ---------------- */

async function refreshAnalytics(){

    try{

        analyticsData = await getAnalytics();

        return analyticsData;

    }

    catch{

        toast("Analytics unavailable.");

        return {};

    }

}


/* ---------------- Revenue ---------------- */

async function refreshRevenue(){

    try{

        revenueData = await getRevenue();

        return revenueData;

    }

    catch{

        toast("Revenue unavailable.");

        return {};

    }

}


/* ---------------- Pending Payments ---------------- */

async function refreshPayments(){

    try{

        paymentData = await getPendingPayments();

        return paymentData;

    }

    catch{

        toast("Unable to load payments.");

        return [];

    }

}


/* ---------------- Approve ---------------- */

async function approve(orderId){

    try{

        await approvePayment(orderId);

        toast("Payment Approved");

        await refreshPayments();

    }

    catch{

        toast("Approval Failed");

    }

}


/* ---------------- Reject ---------------- */

async function reject(orderId){

    try{

        await rejectPayment(orderId);

        toast("Payment Rejected");

        await refreshPayments();

    }

    catch{

        toast("Reject Failed");

    }

}


/* ===========================================================
   BROADCAST
=========================================================== */

async function broadcastMessage(){

    const msg = prompt("Broadcast Message");

    if(!msg) return;

    try{

        await sendBroadcast(msg);

        toast("Broadcast Sent");

    }

    catch{

        toast("Broadcast Failed");

    }

}


/* ===========================================================
   EXPORT
=========================================================== */

async function exportPaymentsCSV(){

    const payments = await refreshPayments();

    if(payments.length===0){

        toast("No payments");

        return;

    }

    let csv="Order ID,Email,Txn ID,Amount,Status\n";

    payments.forEach(p=>{

        csv+=`"${p.order_id}","${p.email}","${p.txn_ref}",${p.amount},"${p.status}"\n`;

    });

    const blob=new Blob([csv],{

        type:"text/csv"

    });

    const url=URL.createObjectURL(blob);

    const a=document.createElement("a");

    a.href=url;

    a.download="payments.csv";

    a.click();

    URL.revokeObjectURL(url);

}


/* ===========================================================
   LIVE REFRESH
=========================================================== */

async function refreshAdmin(){

    if(!localStorage.getItem("admin_key"))

        return;

    try{

        await Promise.all([

            refreshDashboard(),

            refreshAnalytics(),

            refreshRevenue(),

            refreshPayments(),

            loadUsers()

        ]);

    }

    catch(e){

        console.log(e);

    }

}


/* ===========================================================
   AUTO REFRESH
=========================================================== */

setInterval(()=>{

    if(localStorage.getItem("admin_key")){

        refreshAdmin();

    }

},30000);


/* ===========================================================
   ADMIN STARTUP
=========================================================== */

window.addEventListener("load",()=>{

    if(window.location.pathname==="/admin"){

        requireAdmin();

        refreshAdmin();

    }

});
