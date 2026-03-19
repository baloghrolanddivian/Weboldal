const revealItems = document.querySelectorAll(".reveal");
const root = document.documentElement;
let currentReloadToken = null;

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  },
  {
    threshold: 0.15,
  }
);

revealItems.forEach((item) => observer.observe(item));

const counters = document.querySelectorAll("[data-counter]");

const animateCounter = (element) => {
  const targetValue = Number.parseFloat(element.dataset.counter || "0");
  const duration = 1400;
  const startTime = performance.now();
  const hasDecimal = String(targetValue).includes(".");

  const update = (currentTime) => {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const currentValue = targetValue * eased;

    element.textContent = hasDecimal ? currentValue.toFixed(1) : Math.round(currentValue);

    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      element.textContent = hasDecimal ? targetValue.toFixed(1) : String(targetValue);
    }
  };

  requestAnimationFrame(update);
};

const counterObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        animateCounter(entry.target);
        counterObserver.unobserve(entry.target);
      }
    });
  },
  {
    threshold: 0.7,
  }
);

counters.forEach((counter) => counterObserver.observe(counter));

window.addEventListener("pointermove", (event) => {
  const x = `${(event.clientX / window.innerWidth) * 100}%`;
  const y = `${(event.clientY / window.innerHeight) * 100}%`;

  root.style.setProperty("--pointer-x", x);
  root.style.setProperty("--pointer-y", y);
});

const initDivianAI = () => {
  const form = document.getElementById("divian-ai-form");
  const questionInput = document.getElementById("divian-ai-question");
  const submitButton = document.getElementById("divian-ai-submit");
  const statusNode = document.getElementById("divian-ai-status");
  const threadNode = document.getElementById("divian-ai-thread");
  const readyBadge = document.getElementById("divian-ai-ready-badge");

  if (!form || !questionInput || !submitButton || !statusNode || !threadNode || !readyBadge) {
    return;
  }

  let isBusy = false;
  const messages = [
    {
      role: "assistant",
      text: "Írd be a kérdésed. Ha a válasz nem jó, írd meg nyugodtan, hogy mire gondoltál pontosan, és a Divian-AI ahhoz igazodik.",
      sources: [],
      includeInHistory: false,
    },
  ];

  const scrollThreadToBottom = () => {
    window.requestAnimationFrame(() => {
      threadNode.scrollTop = threadNode.scrollHeight;
    });
  };

  const renderThread = () => {
    threadNode.replaceChildren();

    messages.forEach((message) => {
      const item = document.createElement("article");
      item.className = `ai-message ${message.role}${message.pending ? " is-pending" : ""}${message.streaming ? " is-streaming" : ""}${message.error ? " is-error" : ""}`;

      const meta = document.createElement("div");
      meta.className = "ai-message-meta";
      meta.textContent = message.role === "user" ? "Te" : "Divian-AI";

      const bubble = document.createElement("div");
      bubble.className = "ai-bubble";
      bubble.textContent = message.text;

      item.append(meta, bubble);

      if (message.role === "assistant" && Array.isArray(message.sources) && message.sources.length) {
        const sourcesNode = document.createElement("div");
        sourcesNode.className = "ai-message-sources";

        message.sources.forEach((source) => {
          const chip = source === "AI-tudásbázis" ? document.createElement("a") : document.createElement("span");
          chip.className = "ai-source";
          chip.textContent = source;
          if (source === "AI-tudásbázis") {
            chip.href = "/apps/ai-tudasbazis";
          }
          sourcesNode.appendChild(chip);
        });

        item.appendChild(sourcesNode);
      }

      threadNode.appendChild(item);
    });

    scrollThreadToBottom();
  };

  const updateMessage = (messageId, nextValues) => {
    const index = messages.findIndex((message) => message.id === messageId);
    if (index < 0) {
      return false;
    }

    messages[index] = {
      ...messages[index],
      ...nextValues,
    };
    return true;
  };

  const buildHistoryPayload = () =>
    messages
      .filter((message) => message.includeInHistory !== false && !message.pending)
      .map((message) => ({
        role: message.role,
        content: message.text,
      }))
      .slice(-8);

  const updateReadyBadge = (payload) => {
    readyBadge.textContent = payload.message || "Divian-AI státusz ismeretlen.";
    readyBadge.classList.toggle("is-ready", Boolean(payload.knowledge_ready && payload.openai_ready));
    readyBadge.classList.toggle("is-partial", Boolean(payload.knowledge_ready && !payload.openai_ready));
    readyBadge.classList.toggle("is-error", !payload.knowledge_ready);
  };

  const loadStatus = async () => {
    try {
      const response = await fetch("/api/divian-ai/status", {
        headers: {
          Accept: "application/json",
        },
      });
      const payload = await response.json();
      updateReadyBadge(payload);
      statusNode.textContent = payload.message || "A Divian-AI állapota frissítve.";
    } catch (_error) {
      readyBadge.textContent = "A Divian-AI státusza most nem érhető el.";
      readyBadge.classList.add("is-error");
      statusNode.textContent = "A Divian-AI státusza most nem érhető el.";
    }
  };

  const autoResizeInput = () => {
    questionInput.style.height = "auto";
    questionInput.style.height = `${Math.min(questionInput.scrollHeight, 180)}px`;
  };

  const setBusy = (busy) => {
    isBusy = busy;
    submitButton.disabled = busy;
    submitButton.textContent = busy ? "Válaszol..." : "Küldés";
  };

  const wait = (timeout) =>
    new Promise((resolve) => {
      window.setTimeout(resolve, timeout);
    });

  const streamAssistantMessage = async (messageId, fullText, sources) => {
    const segments = fullText.match(/\S+\s*|\n+/g) || [fullText];
    let visibleText = "";

    updateMessage(messageId, {
      text: "",
      pending: false,
      streaming: true,
      sources: [],
    });
    renderThread();

    for (const segment of segments) {
      visibleText += segment;
      updateMessage(messageId, {
        text: visibleText,
        streaming: true,
      });
      renderThread();

      const pace = segment.trim() ? Math.min(68, Math.max(18, segment.replace(/\s+/g, "").length * 8)) : 14;
      await wait(pace);
    }

    updateMessage(messageId, {
      text: fullText,
      streaming: false,
      sources,
    });
    renderThread();
  };

  questionInput.addEventListener("input", () => {
    autoResizeInput();
  });

  questionInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
      return;
    }

    event.preventDefault();
    if (!isBusy) {
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isBusy) {
      return;
    }

    const question = questionInput.value.trim();

    if (!question) {
      statusNode.textContent = "Írj be egy kérdést a Divian-AI számára.";
      questionInput.focus();
      return;
    }

    const pendingId = `pending-${Date.now()}`;
    const history = buildHistoryPayload();
    messages.push({ role: "user", text: question, sources: [] });
    messages.push({
      id: pendingId,
      role: "assistant",
      text: "Keresem a választ a tudástárban...",
      sources: [],
      pending: true,
    });
    renderThread();
    questionInput.value = "";
    autoResizeInput();
    setBusy(true);
    statusNode.textContent = "Divian-AI gondolkodik...";

    try {
      const response = await fetch("/api/divian-ai/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ question, history }),
      });

      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "A Divian-AI most nem tudott válaszolni.");
      }

      statusNode.textContent = "Divian-AI válaszol...";
      await streamAssistantMessage(pendingId, payload.answer || "Nem érkezett válasz.", payload.sources || []);
      statusNode.textContent = "A válasz elkészült.";
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "A Divian-AI most nem érhető el.";

      if (!updateMessage(pendingId, { text: errorMessage, sources: [], pending: false, error: true })) {
        messages.push({
          role: "assistant",
          text: errorMessage,
          sources: [],
          error: true,
        });
      }

      renderThread();
      statusNode.textContent = "A kérdés feldolgozása nem sikerült.";
    } finally {
      setBusy(false);
      questionInput.focus();
      autoResizeInput();
      loadStatus();
    }
  });

  autoResizeInput();
  renderThread();
  loadStatus();
};

initDivianAI();

const enableLiveReload = () => {
  if (!window.EventSource) {
    return;
  }

  const source = new EventSource("/__dev__/events");
  source.addEventListener("reload", (event) => {
    try {
      const payload = JSON.parse(event.data || "{}");
      const nextToken = payload.token;
      if (!nextToken) {
        return;
      }

      if (currentReloadToken === null) {
        currentReloadToken = nextToken;
        return;
      }

      if (currentReloadToken !== nextToken) {
        window.location.reload();
      }
    } catch (_error) {
      // Ignore malformed dev reload payloads and keep the page usable.
    }
  });
};

enableLiveReload();
