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
